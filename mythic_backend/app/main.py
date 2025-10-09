# app/main.py
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException, Depends
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
import re
from dotenv import load_dotenv
import os
from pathlib import Path

# Загружаем .env файл из корня проекта (на уровень выше mythic_backend)
env_path = Path(__file__).parent.parent.parent / '.env'
load_dotenv(env_path)

class NormalizePathMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Убираем повторяющиеся слеши из пути
        path = request.scope['path']
        if '//' in path:
            request.scope['path'] = re.sub(r'/+', '/', path)
        
        response = await call_next(request)
        return response

import asyncio
from pydantic import AnyUrl, BaseModel
import json, logging, datetime
import time

from app.config import settings
from app.services.apify_client import run_actor, fetch_run, fetch_items
from app.services.downloader import download_photos

log = logging.getLogger("api")
app = FastAPI(
    title="Mythic Instagram Parser API",
    description="Парсер постов и текстов из Instagram профилей. Собирает фотографии, тексты, stories и метаданные пользователей Instagram.",
    version="1.0.0"
)

# Простой кэш для статусов
status_cache = {}
CACHE_TTL = 5  # 5 секунд

def get_cached_status(run_id: str):
    """Получить кэшированный статус"""
    if run_id in status_cache:
        cached_time, cached_data = status_cache[run_id]
        if time.time() - cached_time < CACHE_TTL:
            return cached_data
        else:
            del status_cache[run_id]
    return None

def set_cached_status(run_id: str, data: dict):
    """Установить кэшированный статус"""
    status_cache[run_id] = (time.time(), data)

app.add_middleware(NormalizePathMiddleware)

BASE_DIR = Path(__file__).resolve().parent.parent  # mythic_backend/
DATA_DIR = BASE_DIR / "data"

app.mount("/runs", StaticFiles(directory=str(DATA_DIR), html=False), name="runs")

@app.get("/health")
def health_check():
    """Простая проверка работы API"""
    try:
        import psutil
        
        # Get system info
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        return {
            "status": "ok", 
            "message": "Instagram Parser API работает!",
            "timestamp": datetime.datetime.now().isoformat(),
            "system": {
                "memory_percent": memory.percent,
                "disk_percent": disk.percent,
                "cpu_percent": psutil.cpu_percent(interval=0.1),
            },
            "version": "1.0.0"
        }
    except Exception as e:
        # Если psutil недоступен, возвращаем базовый ответ
        return {
            "status": "ok", 
            "message": "Instagram Parser API работает!",
            "timestamp": datetime.datetime.now().isoformat(),
            "version": "1.0.0",
            "error": f"System metrics unavailable: {str(e)}"
        }

# ───────────── / (главная страница) ─────────────────────
@app.get("/")
def read_root():
    """API парсер Instagram - простой JSON ответ"""
    return {
        "service": "Mythic Instagram Parser API",
        "version": "1.0.0",
        "description": "Полный парсер Instagram профилей с комментариями и текстами",
        "features": [
            "✅ Все посты с подписями (captions)",
            "✅ Комментарии под постами (до 100 на пост)",
            "✅ Stories пользователя",
            "✅ Метаданные профиля",
            "✅ Изображения в оригинальном качестве",
            "✅ Лайки, количество комментариев",
            "✅ Timestamps всех активностей"
        ],
        "endpoints": {
            "health": "GET /health - Проверка здоровья сервиса",
            "start_scrape": "GET /start-scrape?url=<instagram_url>&username=<username> - Начать парсинг (асинхронно)",
            "start_scrape_sync": "GET /start-scrape-sync?url=<instagram_url>&username=<username> - Получить JSON сразу (синхронно)",
            "status": "GET /status/{run_id} - Проверить статус парсинга",
            "webhook": "POST /webhook/apify - Webhook для Apify (автоматический)",
            "data": "GET /runs/{run_id}/posts.json - Получить JSON с данными"
        },
        "usage": {
            "async_mode": {
                "step_1": "Отправить GET /start-scrape?url=https://instagram.com/username&username=username",
                "step_2": "Получить runId из ответа",
                "step_3": "Проверять GET /status/{runId} пока stages.data_collected и stages.images_downloaded не станут true",
                "step_4": "Получить полные данные из /runs/{runId}/posts.json"
            },
            "sync_mode": {
                "step_1": "Отправить GET /start-scrape-sync?url=https://instagram.com/username&username=username",
                "step_2": "Получить полный JSON сразу в поле 'data' (ждать 3-10 минут)",
                "note": "Синхронный режим - возвращает все данные сразу, но запрос может длиться до 10 минут"
            }
        },
        "data_collected": {
            "profile": "Username, bio, followers, following, verification status",
            "posts": "Captions, images, videos, likes, comments count, timestamps",
            "comments": "Текст комментария, автор, лайки, timestamp (до 100 на пост)",
            "stories": "Активные stories с изображениями/видео",
            "images": "Все изображения в оригинальном качестве"
        },
        "message": "Используйте /start-scrape для начала полного парсинга Instagram профиля"
        }

# ───────────── /start-scrape ────────────────────────────────
@app.get("/start-scrape")
async def start_scrape(
    url: AnyUrl,
    username: str,  # Username пользователя
):
    """Начать скрапинг Instagram профиля"""
    clean_url = str(url).rstrip("/")
    
    # Используем username как идентификатор
    user_identifier = f"user_{username.lower()}"

    run_input = {
        "directUrls":     [clean_url],
        "resultsType":    "details",
        "scrapeComments": True,        # ✅ ВКЛЮЧАЕМ сбор комментариев
        "commentsLimit": 100,          # ✅ До 100 комментариев на пост
        "scrapeStories": True,         # Собираем сторисы
        "storiesLimit": 10,            # До 10 сторисов
        "resultsLimit": 200,           # Максимум 200 постов
        "addParentData": True,         # Добавляем данные профиля
        "enhanceUserSearchWithFacebookPage": False,  # Отключаем Facebook
    }

    webhook = {
        "eventTypes": ["ACTOR.RUN.SUCCEEDED"],
        "requestUrl": f"{settings.BACKEND_BASE}/webhook/apify",
        "payloadTemplate": (
            '{"runId":"{{runId}}",'
            '"datasetId":"{{defaultDatasetId}}"}'
        ),
    }

    run = await run_actor(run_input, webhooks=[webhook])
    run_id = run["id"]
    
    # Сохраняем информацию о пользователе для этого run_id
    run_dir = Path("data") / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    user_meta = {
        "user_id": user_identifier,
        "username": username,
        "instagram_url": clean_url,
        "created_at": datetime.datetime.now().isoformat()
    }
    (run_dir / "user_meta.json").write_text(json.dumps(user_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    
    log.info("Actor started runId=%s for username=%s", run_id, username)
    return {
        "runId": run_id, 
        "message": "Парсинг начат. Данные будут доступны через несколько минут.",
        "username": username,
        "url": clean_url
    }


# ───────────── /start-scrape-sync ────────────────────────────────
@app.get("/start-scrape-sync")
async def start_scrape_sync(
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
    
    # Таймаут
    raise HTTPException(408, f"Парсинг не завершился за {max_wait_time} секунд. Попробуйте использовать /start-scrape для асинхронного парсинга.")


async def download_photos_async(items, images_dir):
    """Асинхронная загрузка фотографий"""
    try:
        await download_photos(items, images_dir)
        log.info(f"📸 Изображения загружены в {images_dir}")
    except Exception as e:
        log.error(f"❌ Ошибка загрузки изображений: {e}")


@app.post("/webhook/apify")
async def apify_webhook(request: Request, background: BackgroundTasks):
    """Webhook от Apify - вызывается автоматически после завершения парсинга"""
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    run_id = payload.get("runId") or request.headers.get("x-apify-run-id")
    if not run_id:
        raise HTTPException(400, "runId missing")

    dataset_id = payload.get("datasetId")
    if not dataset_id:
        run = await fetch_run(run_id)
        dataset_id = run.get("defaultDatasetId")         

    if not dataset_id:
        raise HTTPException(500, "datasetId unresolved")

    items = await fetch_items(dataset_id)
    run_dir = Path("data") / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Сохраняем JSON с данными
    (run_dir / "posts.json").write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    # Качаем картинки в фоне
    images_dir = run_dir / "images"
    background.add_task(download_photos, items, images_dir)

    log.info(f"Webhook для {run_id} завершен. Данные сохранены в posts.json, изображения загружаются в фоне.")

    return {
        "status": "processing", 
        "runId": run_id, 
        "message": "Данные получены и сохранены. Изображения загружаются.",
        "data_file": f"/runs/{run_id}/posts.json"
    }


@app.get("/status/{run_id}")
def status(run_id: str):
    """Проверить статус парсинга"""
    
    # Проверяем кэш
    cached_status = get_cached_status(run_id)
    if cached_status:
        log.info(f"Status cache hit for {run_id}")
        return cached_status
    
    run_dir = Path("data") / run_id
    
    # Быстрая проверка существования директории
    if not run_dir.exists():
        raise HTTPException(404, "Run not found")
    
    # Кэшируем результаты проверки файлов
    posts_json = run_dir / "posts.json"
    images_dir = run_dir / "images"
    user_meta_file = run_dir / "user_meta.json"
    
    log.info(f"Status check for {run_id}")
    
    # Быстрые проверки без лишних операций
    data_collected = posts_json.exists()
    images_downloaded = images_dir.exists() and any(images_dir.glob("*"))

    # Сообщения в зависимости от статуса
    if images_downloaded and data_collected:
        message = "✅ Парсинг завершен! Данные и изображения готовы."
    elif data_collected:
        message = "⏳ Данные получены, загружаю изображения..."
    else:
        message = "⏳ Парсинг Instagram профиля в процессе..."
    
    # Оптимизированная структура ответа
    status_info = {
        "runId": run_id,
        "message": message,
        "stages": {
            "data_collected": data_collected,
            "images_downloaded": images_downloaded,
            "completed": data_collected and images_downloaded
        },
        "files": {}
    }
    
    # Добавляем пути к файлам если они существуют
    if data_collected:
        status_info["files"]["posts_json"] = f"/runs/{run_id}/posts.json"
    
    if images_downloaded:
        # Подсчитываем количество изображений
        image_count = len(list(images_dir.glob("*")))
        status_info["files"]["images_directory"] = f"/runs/{run_id}/images/"
        status_info["files"]["images_count"] = image_count
    
    # Добавляем информацию о профиле только если данные собраны
    if data_collected and posts_json.exists():
        try:
            posts_data = json.loads(posts_json.read_text(encoding="utf-8"))
            if posts_data and len(posts_data) > 0:
                profile = posts_data[0]
                status_info["profile"] = {
                    "username": profile.get("username"),
                    "fullName": profile.get("fullName"),
                    "biography": profile.get("biography"),
                    "followers": profile.get("followersCount"),
                    "following": profile.get("followsCount"),
                    "posts_count": len(profile.get("latestPosts", [])),
                    "stories_count": len(profile.get("stories", [])),
                    "profile_pic_url": profile.get("profilePicUrl")
                }
    except Exception as e:
            log.warning(f"Error parsing profile data for {run_id}: {e}")
    
    # Добавляем метаданные пользователя
            if user_meta_file.exists():
    try:
        user_meta = json.loads(user_meta_file.read_text(encoding="utf-8"))
            status_info["user_meta"] = user_meta
    except Exception:
            pass
    
    # Кэшируем результат
    set_cached_status(run_id, status_info)
    
    log.info(f"Status response for {run_id}: completed={status_info['stages']['completed']}")
    return status_info


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
