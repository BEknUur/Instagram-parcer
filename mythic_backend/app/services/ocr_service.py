import logging
import asyncio
from pathlib import Path
from typing import Dict, List, Optional
import anyio

log = logging.getLogger("ocr")

# Глобальная переменная для хранения reader (ленивая инициализация)
_reader = None
_reader_lock = asyncio.Lock()


async def _get_reader():
    """Получить или создать EasyOCR reader (ленивая инициализация)"""
    global _reader
    
    if _reader is None:
        async with _reader_lock:
            if _reader is None:  # Double-check
                log.info("Инициализация EasyOCR reader (ru, en)...")
                try:
                    import easyocr
                    # Создаём reader в отдельном потоке, чтобы не блокировать event loop
                    _reader = await anyio.to_thread.run_sync(
                        lambda: easyocr.Reader(['ru', 'en'], gpu=False, verbose=False)
                    )
                    log.info("✅ EasyOCR reader инициализирован")
                except Exception as e:
                    log.error(f"❌ Ошибка инициализации EasyOCR: {e}")
                    raise
    
    return _reader


async def extract_text_from_image(image_path: Path) -> Dict[str, any]:
    """
    Извлекает текст из изображения используя EasyOCR
    
    Args:
        image_path: Путь к изображению
        
    Returns:
        dict: {
            "text": str - весь распознанный текст,
            "confidence": float - средняя уверенность,
            "details": list - детали по каждому найденному блоку текста,
            "has_text": bool - найден ли текст
        }
    """
    if not image_path.exists():
        log.warning(f"Изображение не найдено: {image_path}")
        return {
            "text": "",
            "confidence": 0.0,
            "details": [],
            "has_text": False
        }
    
    try:
        reader = await _get_reader()
        
        # Запускаем OCR в отдельном потоке
        results = await anyio.to_thread.run_sync(
            lambda: reader.readtext(str(image_path))
        )
        
        if not results:
            log.debug(f"Текст не найден в {image_path.name}")
            return {
                "text": "",
                "confidence": 0.0,
                "details": [],
                "has_text": False
            }
        
        # Обрабатываем результаты
        text_blocks = []
        confidences = []
        
        for (bbox, text, confidence) in results:
            text_blocks.append(text)
            confidences.append(confidence)
        
        combined_text = " ".join(text_blocks)
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        
        details = [
            {
                "text": text,
                "confidence": float(confidence)
            }
            for (_, text, confidence) in results
        ]
        
        log.info(f"✅ OCR для {image_path.name}: найдено {len(text_blocks)} блоков текста, уверенность {avg_confidence:.2f}")
        
        return {
            "text": combined_text,
            "confidence": round(avg_confidence, 3),
            "details": details,
            "has_text": True
        }
        
    except Exception as e:
        log.error(f"❌ Ошибка OCR для {image_path}: {e}")
        return {
            "text": "",
            "confidence": 0.0,
            "details": [],
            "has_text": False,
            "error": str(e)
        }


async def extract_text_from_images(image_paths: List[Path]) -> Dict[str, Dict]:
    """
    Извлекает текст из нескольких изображений параллельно
    
    Args:
        image_paths: Список путей к изображениям
        
    Returns:
        dict: {filename: ocr_result}
    """
    results = {}
    
    # Обрабатываем изображения последовательно (EasyOCR не thread-safe для параллельной обработки)
    for image_path in image_paths:
        result = await extract_text_from_image(image_path)
        results[image_path.name] = result
    
    return results

