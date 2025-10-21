# app/main.py
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

import asyncio
from pydantic import AnyUrl
import json, logging, datetime

from app.config import settings
from app.services.apify_client import run_actor, fetch_run, fetch_items, run_comment_scraper
from app.services.downloader import download_photos

log = logging.getLogger("api")
app = FastAPI(
    title="Mythic Instagram Parser API",
    description="Единый endpoint: полный парсинг профиля Instagram (посты, комментарии, stories, highlights) с сохранением JSON и загрузкой медиа.",
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
                
                # Загрузка изображений и OCR в фоне через BackgroundTasks
                images_dir = run_dir / "images"
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


@app.get("/scrape-comments")
async def scrape_comments(
    post_urls: str,
    results_limit: int = 100
):
    """
    Парсинг комментариев под постами Instagram через apify/instagram-comment-scraper
    
    Args:
        post_urls: URL постов через запятую
        results_limit: Максимальное количество комментариев
    """
    
    # Разделяем URL
    urls_list = [url.strip() for url in post_urls.split(',') if url.strip()]
    
    if not urls_list:
        raise HTTPException(400, "Укажите хотя бы один URL поста")
    
    if len(urls_list) > 50:
        raise HTTPException(400, "Максимум 50 постов за запрос")
    
    log.info(f"🚀 Парсинг комментариев для {len(urls_list)} постов")
    
    run_input = {
        "directUrls": urls_list,
        "resultsLimit": results_limit,
    }
    
    try:
        run = await run_comment_scraper(run_input)
        run_id = run["id"]
        
        log.info(f"🔄 Comment scraper запущен, runId={run_id}")
        
        # Ждём завершения (макс 5 минут)
        max_wait_time = 300
        check_interval = 10
        elapsed_time = 0
        
        while elapsed_time < max_wait_time:
            run_status = await fetch_run(run_id)
            status = run_status.get("status")
            
            log.info(f"⏳ Статус: {status} ({elapsed_time}с)")
            
            if status == "SUCCEEDED":
                dataset_id = run_status.get("defaultDatasetId")
                if not dataset_id:
                    raise HTTPException(500, "dataset_id не получен")
                
                comments = await fetch_items(dataset_id, limit=results_limit)
                
                # Сохраняем
                save_dir = Path("data/comments") / run_id
                save_dir.mkdir(parents=True, exist_ok=True)
                (save_dir / "comments.json").write_text(
                    json.dumps(comments, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
                
                log.info(f"✅ Получено {len(comments)} комментариев")
                
                return {
                    "success": True,
                    "runId": run_id,
                    "message": f"✅ Получено {len(comments)} комментариев",
                    "total_comments": len(comments),
                    "posts_count": len(urls_list),
                    "processing_time_seconds": elapsed_time,
                    "comments": comments
                }
                
            elif status == "FAILED":
                raise HTTPException(500, f"Ошибка: {run_status.get('statusMessage')}")
            
            elif status in ["RUNNING", "READY"]:
                await asyncio.sleep(check_interval)
                elapsed_time += check_interval
            else:
                raise HTTPException(500, f"Неожиданный статус: {status}")
        
        raise HTTPException(408, f"Таймаут {max_wait_time}с")
        
    except Exception as e:
        log.error(f"❌ Ошибка парсинга комментариев: {e}")
        raise HTTPException(500, str(e))


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
