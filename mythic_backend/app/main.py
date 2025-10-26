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
    description="Парсинг профилей Instagram: посты с текстами и изображениями.",
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
    """Асинхронный парсинг Instagram профиля с быстрой обработкой ошибок соединения"""
    clean_url = str(url).rstrip("/")
    user_identifier = f"user_{username.lower()}"

    # Проверка валидности URL
    if not clean_url.startswith('https://www.instagram.com/'):
        raise HTTPException(400, "URL должен быть с instagram.com")

    try:
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

        log.info(f"🚀 Асинхронный парсинг начат для {username}, runId={run_id}")

        # Ждем завершения актора (максимум 3 минуты для быстрого отклика)
        max_wait_time = 180  # 3 минуты (уменьшили для быстрого отклика)
        check_interval = 3   # Проверяем каждые 3 секунды
        elapsed_time = 0

        while elapsed_time < max_wait_time:
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
                    "async_request": True,
                    "status": "data_ready"
                }
                (run_dir / "user_meta.json").write_text(json.dumps(user_meta, ensure_ascii=False, indent=2), encoding="utf-8")
                (run_dir / "posts.json").write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
                log.info(f"💾 Сохранены user_meta.json и posts.json ({len(items)} элементов)")

                # Запускаем загрузку изображений в фоне (полностью асинхронно)
                images_dir = run_dir / "images"
                log.info(f"🚀 Запуск асинхронной загрузки изображений в {images_dir}")
                background_tasks.add_task(download_photos_async, items, images_dir, run_id, username)

                log.info(f"✅ Асинхронный парсинг завершен для {username}. Получено {len(items)} элементов.")

                # Возвращаем ответ клиенту СРАЗУ (без ожидания изображений)
                return {
                    "success": True,
                    "runId": run_id,
                    "username": username,
                    "url": clean_url,
                    "message": f"✅ Парсинг завершен! Получено {len(items)} элементов данных. Изображения загружаются в фоне.",
                    "data": items,
                    "status": "data_ready",
                    "stats": {
                        "total_items": len(items),
                        "profile_data": len([item for item in items if item.get("username")]),
                        "processing_time_seconds": elapsed_time,
                        "images_status": "loading"
                    }
                }

            elif status == "FAILED":
                raise HTTPException(500, f"Парсинг не удался: {run_status.get('statusMessage', 'Неизвестная ошибка')}")

            elif status in ["RUNNING", "READY"]:
                # Для первых 30 секунд ждем нормального завершения
                if elapsed_time < 30:
                    await asyncio.sleep(check_interval)
                    elapsed_time += check_interval
                else:
                    # После 30 секунд, если актор еще работает, возвращаем ответ с текущими данными
                    try:
                        dataset_id = run_status.get("defaultDatasetId")
                        if dataset_id:
                            items = await fetch_items(dataset_id, limit=run_input["resultsLimit"])
                            if len(items) > 0:  # Если есть данные, возвращаем их
                                log.info(f"📊 Ранний возврат с {len(items)} элементами для {username}")

                                # Сохраняем данные локально
                                run_dir = Path("data") / run_id
                                run_dir.mkdir(parents=True, exist_ok=True)

                                user_meta = {
                                    "user_id": user_identifier,
                                    "username": username,
                                    "instagram_url": clean_url,
                                    "created_at": datetime.datetime.now().isoformat(),
                                    "async_request": True,
                                    "status": "data_ready"
                                }
                                (run_dir / "user_meta.json").write_text(json.dumps(user_meta, ensure_ascii=False, indent=2), encoding="utf-8")
                                (run_dir / "posts.json").write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

                                # Запускаем загрузку изображений в фоне
                                images_dir = run_dir / "images"
                                background_tasks.add_task(download_photos_async, items, images_dir, run_id, username)

                                return {
                                    "success": True,
                                    "runId": run_id,
                                    "username": username,
                                    "url": clean_url,
                                    "message": f"✅ Данные получены! Получено {len(items)} элементов. Парсинг продолжается в фоне.",
                                    "data": items,
                                    "status": "data_ready",
                                    "stats": {
                                        "total_items": len(items),
                                        "profile_data": len([item for item in items if item.get("username")]),
                                        "processing_time_seconds": elapsed_time,
                                        "images_status": "loading"
                                    }
                                }
                    except Exception as data_error:
                        log.warning(f"Не удалось получить промежуточные данные: {data_error}")

                    # Если нет данных или ошибка, продолжаем ждать
                    await asyncio.sleep(check_interval)
                    elapsed_time += check_interval

            else:
                raise HTTPException(500, f"Неожиданный статус актора: {status}")

        # Если не завершились за установленное время, но есть run_id, возвращаем информацию о продолжении в фоне
        log.info(f"⏰ Парсинг не завершился за {max_wait_time}с, но продолжается в фоне для {run_id}")
        return {
            "success": True,
            "runId": run_id,
            "username": username,
            "url": clean_url,
            "message": f"🔄 Парсинг запущен и продолжается в фоне. Проверьте статус через несколько минут.",
            "data": [],
            "status": "running",
            "stats": {
                "total_items": 0,
                "profile_data": 0,
                "processing_time_seconds": elapsed_time,
                "images_status": "pending"
            }
        }

    except Exception as e:
        log.error(f"❌ Критическая ошибка в start_scrape для {username}: {e}")
        # Если у нас есть run_id, возвращаем информацию о неудаче
        if 'run_id' in locals():
            return {
                "success": False,
                "runId": run_id,
                "username": username,
                "url": clean_url,
                "message": f"❌ Ошибка при парсинге: {str(e)}",
                "data": [],
                "status": "error",
                "stats": {
                    "total_items": 0,
                    "profile_data": 0,
                    "processing_time_seconds": 0,
                    "images_status": "error"
                }
            }

        # Если нет run_id или другая ошибка, возвращаем стандартную ошибку
        raise HTTPException(500, f"Ошибка при запуске парсинга: {str(e)}")




async def download_photos_async(items, images_dir, run_id, username):
    """Асинхронная загрузка фотографий в фоне с обновлением статуса"""
    try:
        log.info(f"🚀 Начинаем асинхронную загрузку изображений для {run_id}")

        # Обновляем статус в user_meta.json
        run_dir = Path("data") / run_id
        user_meta_path = run_dir / "user_meta.json"

        if user_meta_path.exists():
            with open(user_meta_path, 'r', encoding='utf-8') as f:
                user_meta = json.load(f)

            user_meta["status"] = "images_loading"
            user_meta["images_started_at"] = datetime.datetime.now().isoformat()

            with open(user_meta_path, 'w', encoding='utf-8') as f:
                json.dump(user_meta, f, ensure_ascii=False, indent=2)

        # Запускаем загрузку изображений
        from app.services.downloader import download_photos
        download_photos(items, images_dir)

        # Обновляем статус после завершения
        if user_meta_path.exists():
            with open(user_meta_path, 'r', encoding='utf-8') as f:
                user_meta = json.load(f)

            user_meta["status"] = "images_ready"
            user_meta["images_finished_at"] = datetime.datetime.now().isoformat()

            # Подсчитываем количество загруженных изображений
            images_count = 0
            if images_dir.exists():
                for img_file in images_dir.glob("*.jpg"):
                    if not img_file.name.endswith("_placeholder.jpg"):
                        images_count += 1
                for img_file in images_dir.glob("*.jpeg"):
                    if not img_file.name.endswith("_placeholder.jpeg"):
                        images_count += 1
                for img_file in images_dir.glob("*.png"):
                    if not img_file.name.endswith("_placeholder.png"):
                        images_count += 1

            user_meta["images_count"] = images_count

            with open(user_meta_path, 'w', encoding='utf-8') as f:
                json.dump(user_meta, f, ensure_ascii=False, indent=2)

        log.info(f"✅ Изображения загружены для {run_id} ({images_count} файлов)")

    except Exception as e:
        log.error(f"❌ Ошибка асинхронной загрузки изображений для {run_id}: {e}")

        # Обновляем статус с ошибкой
        try:
            run_dir = Path("data") / run_id
            user_meta_path = run_dir / "user_meta.json"

            if user_meta_path.exists():
                with open(user_meta_path, 'r', encoding='utf-8') as f:
                    user_meta = json.load(f)

                user_meta["status"] = "images_error"
                user_meta["images_error"] = str(e)
                user_meta["images_finished_at"] = datetime.datetime.now().isoformat()

                with open(user_meta_path, 'w', encoding='utf-8') as f:
                    json.dump(user_meta, f, ensure_ascii=False, indent=2)
        except Exception as meta_error:
            log.error(f"❌ Ошибка обновления статуса: {meta_error}")


@app.get("/scrape-status")
async def get_scrape_status(run_id: str):
    """Проверить статус парсинга и загрузки изображений"""
    try:
        run_dir = Path("data") / run_id

        if not run_dir.exists():
            raise HTTPException(404, "Парсинг с таким run_id не найден")

        # Читаем метаданные
        user_meta_path = run_dir / "user_meta.json"
        if not user_meta_path.exists():
            raise HTTPException(404, "Метаданные не найдены")

        with open(user_meta_path, 'r', encoding='utf-8') as f:
            user_meta = json.load(f)

        # Читаем посты
        posts_path = run_dir / "posts.json"
        items = []
        if posts_path.exists():
            with open(posts_path, 'r', encoding='utf-8') as f:
                items = json.load(f)

        # Подсчитываем изображения
        images_count = 0
        images_dir = run_dir / "images"
        if images_dir.exists():
            for img_file in images_dir.glob("*.jpg"):
                if not img_file.name.endswith("_placeholder.jpg"):
                    images_count += 1
            for img_file in images_dir.glob("*.jpeg"):
                if not img_file.name.endswith("_placeholder.jpeg"):
                    images_count += 1
            for img_file in images_dir.glob("*.png"):
                if not img_file.name.endswith("_placeholder.png"):
                    images_count += 1

        # Определяем общий статус
        status = user_meta.get("status", "unknown")
        if status == "data_ready" and user_meta.get("images_finished_at"):
            overall_status = "completed"
        elif status == "images_ready":
            overall_status = "completed"
        elif status == "images_loading":
            overall_status = "images_loading"
        elif status == "images_error":
            overall_status = "error"
        else:
            overall_status = status

        return {
            "success": True,
            "run_id": run_id,
            "status": overall_status,
            "details": {
                "data_status": status,
                "images_count": images_count,
                "total_posts": len(items),
                "created_at": user_meta.get("created_at"),
                "images_started_at": user_meta.get("images_started_at"),
                "images_finished_at": user_meta.get("images_finished_at"),
                "images_error": user_meta.get("images_error")
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"❌ Ошибка получения статуса: {e}")
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
