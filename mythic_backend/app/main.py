# app/main.py
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pathlib import Path

import asyncio
from pydantic import AnyUrl
import json, logging, datetime

from app.config import settings
from app.services.apify_client import run_actor, fetch_run, fetch_items
from app.services.downloader import download_photos

log = logging.getLogger("api")
app = FastAPI(
    title="Mythic Instagram Parser API",
    description="Парсинг профилей Instagram: посты с текстами, изображения и OCR распознавание текста с фотографий.",
    version="1.0.0"
)

# Добавляем CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5174",
        "http://localhost:3000",
        "http://104.248.18.254",
        "https://mythicai.me",
        "https://www.mythicai.me"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "instagram-parser", "version": "1.0.0"}


@app.get("/start-scrape")
async def start_scrape(
    url: AnyUrl,
    username: str,
    background_tasks: BackgroundTasks
):
    """Синхронный парсинг Instagram профиля - возвращает полный JSON сразу"""
    clean_url = str(url).rstrip("/")
    
    user_identifier = f"user_{username.lower()}"

    run_input = {
        "directUrls":     [clean_url],
        "resultsType":    "posts",
        "resultsLimit": 50,
        "searchLimit": 1,              # Только один профиль
        "searchType": "user",
    }

    # Запускаем актор БЕЗ webhook - будем ждать завершения
    run = await run_actor(run_input)
    run_id = run["id"]
    
    log.info(f"🚀 Синхронный парсинг начат для {username}, runId={run_id}")
    
    # Ждем завершения актора (максимум 10 минут)
    max_wait_time = 600  # 10 минут
    check_interval = 10  # Проверяем каждые 10 секунд
    elapsed_time = 0
    
    while elapsed_time < max_wait_time:
        try:
            # Проверяем статус актора
            run_status = await fetch_run(run_id)
            status = run_status.get("status")
            
            log.info(f"⏳ Статус парсинга {run_id}: {status} (прошло {elapsed_time}с)")
            
            if status == "SUCCEEDED":
                # Актор завершился успешно - получаем данные
                dataset_id = run_status.get("defaultDatasetId")
                if not dataset_id:
                    raise HTTPException(500, "Не удалось получить dataset_id")
                
                # Получаем данные
                items = await fetch_items(dataset_id, limit=run_input["resultsLimit"])
                
                # Сохраняем данные локально
                run_dir = Path("data") / run_id
                run_dir.mkdir(parents=True, exist_ok=True)
                log.info(f"📁 Создана директория: {run_dir.absolute()}")
                
                user_meta = {
                    "user_id": user_identifier,
                    "username": username,
                    "instagram_url": clean_url,
                    "created_at": datetime.datetime.now().isoformat(),
                    "sync_request": True
                }
                (run_dir / "user_meta.json").write_text(json.dumps(user_meta, ensure_ascii=False, indent=2), encoding="utf-8")
                (run_dir / "posts.json").write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
                log.info(f"💾 Сохранены user_meta.json и posts.json ({len(items)} элементов)")
                
                # Загрузка изображений и OCR в фоне через BackgroundTasks
                images_dir = run_dir / "images"
                log.info(f"🚀 Запуск фоновой загрузки изображений в {images_dir}")
                background_tasks.add_task(download_photos_background, items, images_dir)
                
                log.info(f"✅ Синхронный парсинг завершен для {username}. Получено {len(items)} элементов. OCR запущен в фоне.")
                
                # Возвращаем полный JSON
                return {
                    "success": True,
                    "runId": run_id,
                    "username": username,
                    "url": clean_url,
                    "message": f"✅ Парсинг завершен! Получено {len(items)} элементов данных",
                    "data": items,  # 🎯 ПОЛНЫЙ JSON ОТВЕТ
                    "stats": {
                        "total_items": len(items),
                        "profile_data": len([item for item in items if item.get("username")]),
                        "processing_time_seconds": elapsed_time
                    }
                }
                
            elif status == "FAILED":
                raise HTTPException(500, f"Парсинг не удался: {run_status.get('statusMessage', 'Неизвестная ошибка')}")
            
            elif status in ["RUNNING", "READY"]:
                # Актор еще работает - ждем
                await asyncio.sleep(check_interval)
                elapsed_time += check_interval
            else:
                raise HTTPException(500, f"Неожиданный статус актора: {status}")
                
        except Exception as e:
            if elapsed_time > 60:  # Если прошло больше минуты, возвращаем ошибку
                raise HTTPException(500, f"Ошибка при парсинге: {str(e)}")
            else:
                # Первые попытки могут не сработать - ждем
                await asyncio.sleep(check_interval)
                elapsed_time += check_interval
    
    raise HTTPException(408, f"Парсинг не завершился за {max_wait_time} секунд.")




def download_photos_background(items, images_dir):
    """Фоновая загрузка фотографий с OCR (синхронная для BackgroundTasks)"""
    try:
        log.info(f"🚀 Начинаем фоновую загрузку изображений и OCR для {images_dir}")
        download_photos(items, images_dir)
        log.info(f"✅ Изображения загружены и OCR выполнен в {images_dir}")
    except Exception as e:
        log.error(f"❌ Ошибка фоновой загрузки изображений: {e}")


@app.get("/get-ocr-results")
async def get_ocr_results(run_id: str):
    """
    Получить OCR результаты для конкретного run_id
    
    Args:
        run_id: ID запуска парсинга
    """
    try:
        run_dir = Path("data") / run_id
        ocr_file = run_dir / "images" / "ocr_results.json"
        
        if not ocr_file.exists():
            raise HTTPException(404, "OCR результаты не найдены. Возможно, обработка еще не завершена.")
        
        ocr_data = json.loads(ocr_file.read_text(encoding="utf-8"))
        
        # Статистика
        total_images = len(ocr_data)
        images_with_text = sum(1 for r in ocr_data.values() if r.get("has_text"))
        
        return {
            "success": True,
            "run_id": run_id,
            "total_images": total_images,
            "images_with_text": images_with_text,
            "ocr_results": ocr_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"❌ Ошибка получения OCR результатов: {e}")
        raise HTTPException(500, str(e))


@app.get("/get-images")
async def get_images(run_id: str):
    """
    Получить список всех изображений для run_id
    
    Args:
        run_id: ID запуска парсинга
    """
    try:
        run_dir = Path("data") / run_id / "images"
        
        if not run_dir.exists():
            raise HTTPException(404, "Папка с изображениями не найдена")
        
        # Собираем все изображения (кроме placeholder)
        images = []
        for img_file in sorted(run_dir.glob("*.jpg")):
            if not img_file.name.endswith("_placeholder.jpg"):
                images.append(img_file.name)
        
        for img_file in sorted(run_dir.glob("*.jpeg")):
            if not img_file.name.endswith("_placeholder.jpeg"):
                images.append(img_file.name)
        
        for img_file in sorted(run_dir.glob("*.png")):
            if not img_file.name.endswith("_placeholder.png"):
                images.append(img_file.name)
        
        log.info(f"📸 Найдено {len(images)} изображений для run_id={run_id}")
        
        return {
            "success": True,
            "run_id": run_id,
            "total_images": len(images),
            "images": images
        }
        
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"❌ Ошибка получения списка изображений: {e}")
        raise HTTPException(500, str(e))


@app.get("/image/{run_id}/{filename}")
async def get_image(run_id: str, filename: str):
    """
    Получить конкретное изображение
    
    Args:
        run_id: ID запуска парсинга
        filename: Имя файла изображения
    """
    try:
        # Безопасность: проверяем, что filename не содержит путей
        if "/" in filename or "\\" in filename or ".." in filename:
            raise HTTPException(400, "Недопустимое имя файла")
        
        image_path = Path("data") / run_id / "images" / filename
        
        if not image_path.exists():
            raise HTTPException(404, "Изображение не найдено")
        
        return FileResponse(image_path)
        
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"❌ Ошибка отдачи изображения: {e}")
        raise HTTPException(500, str(e))
