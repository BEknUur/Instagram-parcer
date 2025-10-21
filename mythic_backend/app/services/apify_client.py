from __future__ import annotations
import anyio, logging
from apify_client import ApifyClient
from apify_client.errors import ApifyApiError
from app.config import settings

log = logging.getLogger("apify")
_client = ApifyClient(settings.APIFY_TOKEN)



def _normalize_webhooks(webhooks: list[dict]) -> list[dict]:
    out = []
    for wh in webhooks:
        out.append(
            {
                "event_types":     wh.get("event_types") or wh.get("eventTypes"),
                "request_url":     wh.get("request_url") or wh.get("requestUrl"),
                "payload_template": wh.get("payload_template") or wh.get("payloadTemplate"),
                "idempotency_key": wh.get("idempotency_key") or wh.get("idempotencyKey"),
            }
        )
    return out


async def run_actor(run_input: dict, webhooks: list[dict] | None = None) -> dict:
    """Запускаем Actor без блокировки event-loop."""
    def _sync():
        act = _client.actor(settings.ACTOR_ID)
        return act.call(
            run_input=run_input,
            webhooks=_normalize_webhooks(webhooks) if webhooks else None,
        )
    return await anyio.to_thread.run_sync(_sync)


async def fetch_run(run_id: str) -> dict:
    """Получаем объект Run по runId (блокирующий SDK в пуле потоков)."""
    return await anyio.to_thread.run_sync(lambda: _client.run(run_id).get())


async def fetch_items(dataset_id: str, limit: int = 1000, retries: int = 10, delay: float = 2.0) -> list[dict]:
    """Скачиваем все items; повторяем, пока датасет не станет доступен."""
    for attempt in range(1, retries + 1):
        try:
            return await anyio.to_thread.run_sync(
                lambda: _client.dataset(dataset_id).list_items(limit=limit).items
            )
        except ApifyApiError as err:
            if getattr(err, "status_code", None) != 404:
                log.error("Apify error: %s", err)
                raise
            log.warning("Dataset %s not ready (try %s/%s) — wait %.1fs",
                        dataset_id, attempt, retries, delay)
            await anyio.sleep(delay)
            delay *= 1.5
    log.error("Dataset %s not found after %s retries", dataset_id, retries)
    return []


async def run_comment_scraper(run_input: dict) -> dict:
    """Запускаем Instagram Comment Scraper Actor (apify/instagram-comment-scraper)."""
    def _sync():
        # Используем Actor по имени apify/instagram-comment-scraper
        act = _client.actor("apify/instagram-comment-scraper")
        return act.call(run_input=run_input)
    return await anyio.to_thread.run_sync(_sync)
