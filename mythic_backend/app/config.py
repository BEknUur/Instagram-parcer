from pydantic_settings import BaseSettings 
from typing import Optional

class Settings(BaseSettings):
    """Настройки для Instagram Parser API - только необходимое"""
    
    # Apify configuration (обязательно)
    APIFY_TOKEN: str 
    ACTOR_ID: str = "apify/instagram-profile-scraper"
    BACKEND_BASE: str = "http://localhost:8001"
    
    # Database configuration (опционально)
    DATABASE_URL: Optional[str] = "postgresql+asyncpg://mythic:mythic_password_2024@database:5432/mythic"
    ASYNC_DATABASE_URL: Optional[str] = None

    class Config:
        env_file = ".env"
    
    @property
    def get_async_database_url(self) -> str:
        """Get async database URL, deriving from DATABASE_URL if ASYNC_DATABASE_URL is not set"""
        if self.ASYNC_DATABASE_URL:
            return self.ASYNC_DATABASE_URL
        
        # Convert sync URL to async URL
        if self.DATABASE_URL and self.DATABASE_URL.startswith("postgresql://"):
            return self.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
        
        return "postgresql+asyncpg://mythic:mythic_password_2024@database:5432/mythic"

settings = Settings()
