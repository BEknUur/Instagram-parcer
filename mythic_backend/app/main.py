# app/main.py
from fastapi import FastAPI, HTTPException
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
    description="Единый endpoint: полный парсинг профиля Instagram (посты, комментарии, stories, highlights) с сохранением JSON и загрузкой медиа.",
    version="1.0.0"
)

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "instagram-parser", "version": "1.0.0"}


@app.get("/start-scrape")
async def start_scrape(
    url: AnyUrl,
    username: str
):
    """Синхронный парсинг Instagram профиля - возвращает полный JSON сразу"""
    clean_url = str(url).rstrip("/")
    
    user_identifier = f"user_{username.lower()}"

    run_input = {
        "directUrls":     [clean_url],
        "resultsType":    "details",
        "scrapeComments": True,        # ✅ ВКЛЮЧАЕМ сбор комментариев
        "commentsLimit": 100,          # ✅ До 100 комментариев на пост
        "scrapeStories": True,         # Собираем сторисы
        "storiesLimit": 10,            # До 10 сторисов
        "scrapeHighlights": True,      # ✅ Собираем актуальное (highlights)
        "highlightsLimit": 20,         # Лимит элементов в актуальном
        "resultsLimit": 200,           # Максимум 200 постов
        "addParentData": True,         # Добавляем данные профиля
        "enhanceUserSearchWithFacebookPage": False,  # Отключаем Facebook
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
                items = await fetch_items(dataset_id)
                
                # Сохраняем данные локально (опционально)
                run_dir = Path("data") / run_id
                run_dir.mkdir(parents=True, exist_ok=True)
                
                user_meta = {
                    "user_id": user_identifier,
                    "username": username,
                    "instagram_url": clean_url,
                    "created_at": datetime.datetime.now().isoformat(),
                    "sync_request": True
                }
                (run_dir / "user_meta.json").write_text(json.dumps(user_meta, ensure_ascii=False, indent=2), encoding="utf-8")
                (run_dir / "posts.json").write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
                
                # Запускаем загрузку изображений в фоне (не ждем)
                images_dir = run_dir / "images"
                asyncio.create_task(download_photos_async(items, images_dir))
                
                log.info(f"✅ Синхронный парсинг завершен для {username}. Получено {len(items)} элементов")
                
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
                        "posts_with_comments": len([item for item in items if item.get("latestPosts") and any(post.get("commentsCount", 0) > 0 for post in item.get("latestPosts", []))]),
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


async def download_photos_async(items, images_dir):
    """Асинхронная загрузка фотографий"""
    try:
        await download_photos(items, images_dir)
        log.info(f"📸 Изображения загружены в {images_dir}")
    except Exception as e:
        log.error(f"❌ Ошибка загрузки изображений: {e}")
