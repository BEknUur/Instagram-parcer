import asyncio
import httpx, logging, mimetypes, json
from pathlib import Path
from typing import List, Dict

log = logging.getLogger("downloader")


# ─────────────────── сбор ссылок ────────────────────────────────────────────
def _collect_urls(items: List[Dict]) -> List[str]:
    """Собираем URL фото ТОЛЬКО из обычных постов (не reels/видео)."""
    urls: list[str] = []
    
    log.info(f"🔍 Обрабатываем {len(items)} элементов для поиска изображений")
    
    # Логируем структуру для отладки
    if items and len(items) > 0:
        first_item_keys = list(items[0].keys())
        log.info(f"Ключи первого элемента: {first_item_keys}")
        
        # Проверяем разные форматы данных
        if "latestPosts" in items[0]:
            log.info(f"✅ Формат профиля: найдено {len(items[0].get('latestPosts', []))} постов")
        elif "displayUrl" in items[0] or "images" in items[0]:
            log.info(f"✅ Формат постов: элементы являются постами напрямую")
        else:
            log.warning(f"⚠️ Неизвестный формат данных!")

    for idx, item in enumerate(items):
        # Вариант 1: Данные - профиль с latestPosts
        if "latestPosts" in item:
            log.info(f"📦 Элемент {idx}: профиль, обрабатываем latestPosts")
            posts = item.get("latestPosts", [])
            for post_idx, post in enumerate(posts):
                post_type = post.get("type", "Unknown")
                
                # ВАЖНО: Берем фото ТОЛЬКО из Image и Sidecar (карусели)
                # Игнорируем Video, Reel, IGTV - даже если там есть превью
                if post_type not in ["Image", "Sidecar"]:
                    log.info(f"  ⏭️ Пост {post_idx}: {post_type} - НЕ фото, пропускаем")
                    continue
                
                log.info(f"  📸 Пост {post_idx}: {post_type} - обрабатываем фото")
                
                # Берем главное изображение
                if post.get("displayUrl"):
                    urls.append(post["displayUrl"])
                    log.debug(f"    ✅ Добавлено displayUrl")
                
                # Берем все изображения из массива (для каруселей)
                if post.get("images"):
                    image_count = len(post["images"])
                    urls.extend(post["images"])
                    log.debug(f"    ✅ Добавлено {image_count} изображений из массива")
                
                # Обрабатываем childPosts для каруселей
                for child_idx, child in enumerate(post.get("childPosts", [])):
                    if child.get("displayUrl"):
                        urls.append(child["displayUrl"])
                        log.debug(f"    ✅ Добавлено childPost {child_idx}")
        
        # Вариант 2: Данные - это уже посты напрямую (режим "posts")
        elif "displayUrl" in item or "images" in item:
            post_type = item.get("type", "Unknown")
            
            # ВАЖНО: Берем фото ТОЛЬКО из Image и Sidecar
            if post_type not in ["Image", "Sidecar"]:
                log.info(f"  ⏭️ Элемент {idx}: {post_type} - НЕ фото, пропускаем")
                continue
            
            log.info(f"  📸 Элемент {idx}: {post_type} - обрабатываем фото")
            
            # Берем главное изображение
            if item.get("displayUrl"):
                urls.append(item["displayUrl"])
                log.debug(f"    ✅ Добавлено displayUrl")
            
            # Берем все изображения из массива
            if item.get("images"):
                image_count = len(item["images"])
                urls.extend(item["images"])
                log.debug(f"    ✅ Добавлено {image_count} изображений")
            
            # Обрабатываем childPosts
            for child_idx, child in enumerate(item.get("childPosts", [])):
                if child.get("displayUrl"):
                    urls.append(child["displayUrl"])
                    log.debug(f"    ✅ Добавлено childPost {child_idx}")

    # Удаляем дубликаты, сохраняя порядок
    seen = set()
    out = []
    for u in urls:
        if u and u not in seen:
            out.append(u)
            seen.add(u)
    
    # Ограничиваем до 50 фото
    max_photos = 50
    if len(out) > max_photos:
        log.info(f"⚠️ Найдено {len(out)} фото, ограничиваем до {max_photos}")
        out = out[:max_photos]
    
    log.info(f"✅ Итого будет загружено: {len(out)} фото")
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
            log.warning("❌ Фотографии не найдены — нечего загружать")
            return

        folder.mkdir(parents=True, exist_ok=True)
        log.info(f"📥 Начинаем загрузку {len(urls)} фотографий в {folder}")

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
            future.result(timeout=300)  # 5 минут на загрузку и OCR до 50 фото
        except RuntimeError:
            asyncio.run(main())
            
        log.info(f"✅ Загрузка и OCR завершены ({len(urls)} фото обработано)")
        
    except Exception as e:
        log.error(f"Critical error in download_photos: {e}")
        try:
            folder.mkdir(parents=True, exist_ok=True)
            _create_placeholder_image(folder, 1)
        except Exception as fallback_error:
            log.error(f"Failed to create fallback image: {fallback_error}")
