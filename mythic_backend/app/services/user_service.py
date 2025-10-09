from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from ..models import User, Book, ProcessingSession
from typing import Optional, List
import json

class UserService:
    
    @staticmethod
    async def get_or_create_user(
        db: AsyncSession,
        clerk_user_id: str,
        email: Optional[str] = None,
        full_name: Optional[str] = None
    ) -> User:
        """Получить или создать пользователя по Clerk ID"""
        # Попытка найти существующего пользователя
        stmt = select(User).where(User.clerk_user_id == clerk_user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if user:
            # Обновляем данные если они изменились
            if user.email != email or user.full_name != full_name:
                user.email = email
                user.full_name = full_name
                await db.commit()
            return user
        
        # Создаем нового пользователя
        user = User(
            clerk_user_id=clerk_user_id,
            email=email,
            full_name=full_name
        )
        db.add(user)
        await db.commit()
        return user
    
    @staticmethod
    async def get_user_by_clerk_id(db: AsyncSession, clerk_user_id: str) -> Optional[User]:
        """Получить пользователя по Clerk ID"""
        stmt = select(User).where(User.clerk_user_id == clerk_user_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_user_with_books(db: AsyncSession, clerk_user_id: str) -> Optional[User]:
        """Получить пользователя с его книгами"""
        stmt = (
            select(User)
            .options(selectinload(User.books))
            .where(User.clerk_user_id == clerk_user_id)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_user_books(db: AsyncSession, clerk_user_id: str) -> List[Book]:
        """Получить все книги пользователя"""
        stmt = (
            select(Book)
            .join(User)
            .where(User.clerk_user_id == clerk_user_id)
            .order_by(Book.created_at.desc())
        )
        result = await db.execute(stmt)
        return result.scalars().all()
    
    @staticmethod
    async def create_processing_session(
        db: AsyncSession,
        run_id: str,
        clerk_user_id: str,
        instagram_url: str
    ) -> ProcessingSession:
        """Создать сессию обработки"""
        user = await UserService.get_or_create_user(db, clerk_user_id)
        
        session = ProcessingSession(
            run_id=run_id,
            user_id=user.id,
            instagram_url=instagram_url,
            status="started"
        )
        db.add(session)
        await db.commit()
        return session
    
    @staticmethod
    async def update_processing_session(
        db: AsyncSession,
        run_id: str,
        status: Optional[str] = None,
        current_stage: Optional[str] = None,
        progress_percentage: Optional[int] = None,
        error_message: Optional[str] = None
    ) -> Optional[ProcessingSession]:
        """Обновить сессию обработки"""
        stmt = select(ProcessingSession).where(ProcessingSession.run_id == run_id)
        result = await db.execute(stmt)
        session = result.scalar_one_or_none()
        
        if not session:
            return None
        
        if status is not None:
            session.status = status
        if current_stage is not None:
            session.current_stage = current_stage
        if progress_percentage is not None:
            session.progress_percentage = progress_percentage
        if error_message is not None:
            session.error_message = error_message
        
        await db.commit()
        return session
    
    @staticmethod
    async def get_processing_session(db: AsyncSession, run_id: str) -> Optional[ProcessingSession]:
        """Получить сессию обработки"""
        stmt = select(ProcessingSession).where(ProcessingSession.run_id == run_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none() 