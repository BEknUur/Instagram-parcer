import asyncio
import httpx, logging, mimetypes, json
from pathlib import Path
from typing import List, Dict

log = logging.getLogger("downloader")


# ─────────────────── сбор ссылок ────────────────────────────────────────────
def _collect_urls(items: List[Dict]) -> List[str]:
    """Ищем displayUrl и images во всех latestPosts, childPosts и stories."""
    urls: list[str] = []

    def walk(post: Dict):
        if post.get("displayUrl"):
            urls.append(post["displayUrl"])
        urls.extend(post.get("images", []))
        for child in post.get("childPosts", []):
            walk(child)

    for root in items:
        for p in root.get("latestPosts", []):
            walk(p)
        
        # Собираем URL из сторисов
        for story in root.get("stories", []):
            if story.get("displayUrl"):
                urls.append(story["displayUrl"])
            # Если есть массив изображений в сторисе
            if story.get("images"):
                urls.extend(story["images"])
            # Если есть видео превью в сторисе
            if story.get("videoUrl"):
                urls.append(story["videoUrl"])

        # Собираем URL из актуального (highlights)
        for highlight in root.get("highlights", []):
            # Некоторые скриптеры отдают highlight.items
            for item in highlight.get("items", []):
                if item.get("displayUrl"):
                    urls.append(item["displayUrl"])
                if item.get("images"):
                    urls.extend(item["images"])
                if item.get("videoUrl"):
                    urls.append(item["videoUrl"])
            # На случай плоской структуры без items
            if highlight.get("displayUrl"):
                urls.append(highlight["displayUrl"])
            if highlight.get("images"):
                urls.extend(highlight["images"])
            if highlight.get("videoUrl"):
                urls.append(highlight["videoUrl"])

    # удаляем дубликаты, сохраняя порядок
    seen = set()
    out = []
    for u in urls:
        if u not in seen:
            out.append(u)
            seen.add(u)
    return out


# ─────────────────── скачивание с retry логикой ─────────────────────────────
async def _save(url: str, folder: Path, client: httpx.AsyncClient, idx: int, max_retries: int = 3):
    """Скачивает изображение с повторными попытками при ошибках соединения"""
    for attempt in range(max_retries + 1):
        try:
            # Увеличиваем таймаут и добавляем задержку между попытками
            timeout = httpx.Timeout(30.0, connect=10.0)
            r = await client.get(url, follow_redirects=True, timeout=timeout)
            r.raise_for_status()
            
            # получаем расширение по Content-Type, fallback = .jpg
            ext = mimetypes.guess_extension(r.headers.get("content-type", "")) or ".jpg"
            fname = folder / f"{idx:03d}{ext}"
            fname.write_bytes(r.content)
            log.debug("saved %s", fname.name)
            return  # Успешно скачали, выходим
            
        except (httpx.ConnectError, httpx.TimeoutException, httpx.RequestError) as e:
            if attempt < max_retries:
                wait_time = 2 ** attempt  # Экспоненциальная задержка
                log.warning(f"Attempt {attempt + 1} failed for {url}: {e}. Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
            else:
                log.error(f"Failed to download {url} after {max_retries + 1} attempts: {e}")
                # Создаем заглушку для отсутствующего изображения
                _create_placeholder_image(folder, idx)
        except Exception as e:
            log.error(f"Unexpected error downloading {url}: {e}")
            _create_placeholder_image(folder, idx)
            return


def _create_placeholder_image(folder: Path, idx: int):
    """Создает изображение-заглушку для отсутствующих файлов"""
    try:
        from PIL import Image, ImageDraw, ImageFont
        
        # Создаем простое изображение-заглушку
        img = Image.new('RGB', (400, 300), color='#f0f0f0')
        draw = ImageDraw.Draw(img)
        
        # Добавляем текст
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
        except:
            font = ImageFont.load_default()
        
        text = f"Image {idx}\nNot Available"
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        x = (400 - text_width) // 2
        y = (300 - text_height) // 2
        draw.text((x, y), text, fill='#666666', font=font, align='center')
        
        # Сохраняем заглушку
        fname = folder / f"{idx:03d}_placeholder.jpg"
        img.save(fname, format='JPEG', quality=80)
        log.info(f"Created placeholder image: {fname.name}")
        
    except Exception as e:
        log.error(f"Failed to create placeholder image: {e}")


async def _run_ocr_on_images(folder: Path):
    """Запускает OCR на всех изображениях в папке и сохраняет результаты"""
    try:
        from app.services.ocr_service import extract_text_from_images
        
        # Находим все изображения (исключая placeholder'ы)
        image_files = [
            f for f in folder.glob("*.jpg") 
            if not f.name.endswith("_placeholder.jpg")
        ]
        image_files.extend([f for f in folder.glob("*.jpeg") if not f.name.endswith("_placeholder.jpeg")])
        image_files.extend([f for f in folder.glob("*.png") if not f.name.endswith("_placeholder.png")])
        
        if not image_files:
            log.warning(f"No images found in {folder} for OCR")
            return
        
        log.info(f"🔍 Starting OCR for {len(image_files)} images in {folder}")
        
        # Запускаем OCR
        ocr_results = await extract_text_from_images(image_files)
        
        # Сохраняем результаты
        ocr_file = folder / "ocr_results.json"
        ocr_file.write_text(
            json.dumps(ocr_results, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        
        # Подсчитываем статистику
        images_with_text = sum(1 for r in ocr_results.values() if r.get("has_text"))
        log.info(f"✅ OCR completed: {images_with_text}/{len(image_files)} images contain text")
        
    except Exception as e:
        log.error(f"❌ Error during OCR processing: {e}")


def download_photos(items: List[Dict], folder: Path):
    """Синхронная обёртка для Starlette BackgroundTask с улучшенной обработкой ошибок."""
    try:
        urls = _collect_urls(items)
        if not urls:
            log.warning("no image urls found — nothing to download")
            return

        # Ограничиваем до первых 15 фотографий для оптимизации
        urls = urls[:15]
        log.info("limiting to first %s images for optimal performance", len(urls))

        folder.mkdir(parents=True, exist_ok=True)
        log.info("downloading %s images → %s", len(urls), folder)

        async def main():
            # Настройки клиента с более надежными параметрами
            limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
            timeout = httpx.Timeout(30.0, connect=10.0)
            
            async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:
                # Ограничиваем количество одновременных загрузок
                semaphore = asyncio.Semaphore(3)
                
                async def download_with_semaphore(url: str, idx: int):
                    async with semaphore:
                        await _save(url, folder, client, idx)
                
                tasks = [download_with_semaphore(u, i) for i, u in enumerate(urls, 1)]
                await asyncio.gather(*tasks, return_exceptions=True)
            
            # После загрузки изображений запускаем OCR
            log.info("📸 Images downloaded, starting OCR processing...")
            await _run_ocr_on_images(folder)

        
        try:
            loop = asyncio.get_running_loop()
            future = asyncio.run_coroutine_threadsafe(main(), loop)
            future.result(timeout=180)  # Увеличили таймаут для OCR
        except RuntimeError:
            asyncio.run(main())
            
        log.info("download and OCR completed (%s urls processed)", len(urls))
        
    except Exception as e:
        log.error(f"Critical error in download_photos: {e}")
        try:
            folder.mkdir(parents=True, exist_ok=True)
            _create_placeholder_image(folder, 1)
        except Exception as fallback_error:
            log.error(f"Failed to create fallback image: {fallback_error}")
