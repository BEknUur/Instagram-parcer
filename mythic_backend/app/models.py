from __future__ import annotations

import uuid
from sqlalchemy import (
    Column,
    String,
    DateTime,
    Boolean,
    Text,
    ForeignKey,
    Integer,
    JSON,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID  # ← тип UUID для Postgres
from datetime import datetime

Base = declarative_base()


# ────────────────────────────────────
#            USERS
# ────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clerk_user_id = Column(String, unique=True, nullable=False, index=True)

    email = Column(String, nullable=True)
    full_name = Column(String, nullable=True)
   # has_seen_tour = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # связь 1-N → Book
    books = relationship("Book", back_populates="user", cascade="all, delete-orphan")
    processing_sessions = relationship("ProcessingSession", back_populates="user")


# ────────────────────────────────────
#            BOOKS
# ────────────────────────────────────
class Book(Base):
    __tablename__ = "books"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )

    run_id = Column(String, nullable=False, index=True)  # ID из Apify
    title = Column(String, nullable=False)

    # Информация профиля Instagram
    profile_username = Column(String)
    profile_full_name = Column(String)
    profile_followers = Column(Integer)
    profile_posts_count = Column(Integer)

    # Файлы
    html_path = Column(String)
    pdf_path = Column(String)
    images_path = Column(String)

    # Статус
    is_completed = Column(Boolean, default=False)
    has_html = Column(Boolean, default=False)
    has_pdf = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Доп. данные (JSON-строкой)
    book_metadata = Column(JSON)

    # связь N-1 → User
    user = relationship("User", back_populates="books")


# ────────────────────────────────────
#       PROCESSING SESSIONS
# ────────────────────────────────────
class ProcessingSession(Base):
    """Отслеживание прогресса Apify-запуска"""

    __tablename__ = "processing_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(String, unique=True, nullable=False, index=True)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    instagram_url = Column(String, nullable=False)

    # Статус
    status = Column(String, default="started")  # started | scraping | building | ...
    current_stage = Column(String)
    progress_percentage = Column(Integer, default=0)
    error_message = Column(Text)

    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))

    # связь N-1 → User
    user = relationship("User", back_populates="processing_sessions")
