# app/database.py
from __future__ import annotations

import os
from typing import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.orm import sessionmaker, Session

from .config import settings
from .models import Base

# -----------------------------------------------------------
# 1.  URLs
# -----------------------------------------------------------
DATABASE_URL: str = settings.DATABASE_URL
ASYNC_DATABASE_URL: str = settings.get_async_database_url

# -----------------------------------------------------------
# 2.  Движки
# -----------------------------------------------------------
#   sync – нужен для миграций и create_all / drop_all
sync_engine = create_engine(
    DATABASE_URL,
    echo=False,          # True → лог SQL
    pool_size=20,
    max_overflow=30,
    pool_pre_ping=True,
)

#   async – основная работа приложения
async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    echo=False,
    pool_size=20,
    max_overflow=30,
    pool_pre_ping=True,
)

# -----------------------------------------------------------
# 3.  Фабрики сессий
# -----------------------------------------------------------
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=sync_engine,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# -----------------------------------------------------------
# 4.  Инициализация схемы
# -----------------------------------------------------------
def create_tables() -> None:
    """
    Создать (или, при FORCE_DB_RESET=1, пересоздать) таблицы в базе.

    ▸ В dev-среде удобно дропать всё перед стартом контейнера,
      чтобы схема всегда соответствовала актуальным моделям.
    ▸ В production НЕ включайте FORCE_DB_RESET – используйте Alembic.
    """
    if os.getenv("FORCE_DB_RESET") == "1":
        print("[DB] ⚠️  Dropping all tables (FORCE_DB_RESET=1)")
        Base.metadata.drop_all(bind=sync_engine)

    # checkfirst=True – создаст только отсутствующие таблицы
    Base.metadata.create_all(bind=sync_engine)


# -----------------------------------------------------------
# 5.  Helpers для зависимостей FastAPI
# -----------------------------------------------------------
def get_sync_db() -> Session:
    """Синхронная сессия (редко нужна, например, для Alembic-скриптов)."""
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """Асинхронная сессия (используется приложением)."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_optional_async_db() -> AsyncGenerator[AsyncSession | None, None]:
    """Опциональная асинхронная сессия - возвращает None если база недоступна."""
    try:
        async with AsyncSessionLocal() as session:
            try:
                yield session
            finally:
                await session.close()
    except Exception as e:
        print(f"Database unavailable: {e}")
        yield None


# alias: import → Depends(get_db)
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async for s in get_async_db():
        yield s


# alias: import → Depends(get_optional_db)  
async def get_optional_db() -> AsyncGenerator[AsyncSession | None, None]:
    async for s in get_optional_async_db():
        yield s
