from pydantic_settings import BaseSettings 

class Settings(BaseSettings):
    """Настройки для Instagram Parser API - только необходимое"""
    
    # Apify configuration (обязательно)
    APIFY_TOKEN: str 
    ACTOR_ID: str = "apify/instagram-profile-scraper"
    BACKEND_BASE: str = "http://localhost:8001"

    class Config:
        env_file = ".env"

settings = Settings()
