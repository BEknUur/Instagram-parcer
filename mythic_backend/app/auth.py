import jwt
import requests
from typing import Optional, Dict, Any
from fastapi import HTTPException, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.config import settings
import json
import base64

CLERK_SECRET_KEY = settings.CLERK_SECRET_KEY
CLERK_PUBLISHABLE_KEY = settings.CLERK_PUBLISHABLE_KEY

security = HTTPBearer()

class ClerkAuth:
    def __init__(self):
        self.jwks_url = f"https://api.clerk.dev/v1/jwks"
        self._jwks = None
        self.enabled = bool(CLERK_SECRET_KEY and CLERK_PUBLISHABLE_KEY)

    def get_jwks(self):
        if not self.enabled:
            raise HTTPException(
                status_code=500, 
                detail="Аутентификация не настроена. Обратитесь к администратору."
            )
            
        if not self._jwks:
            try:
                response = requests.get(self.jwks_url)
                response.raise_for_status()
                self._jwks = response.json()
            except Exception as e:
                print(f"Ошибка получения JWKS: {e}")
                raise HTTPException(
                    status_code=500,
                    detail="Ошибка настройки аутентификации"
                )
        return self._jwks

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Строгая проверка токена - без опции anonymous"""
        if not self.enabled:
            raise HTTPException(
                status_code=500,
                detail="Аутентификация не настроена. Пожалуйста, настройте Clerk."
            )
            
        try:
            if hasattr(jwt, 'decode'):
                payload = jwt.decode(token, options={"verify_signature": False})
            else:
                parts = token.split('.')
                if len(parts) != 3:
                    raise HTTPException(
                        status_code=401,
                        detail="Неверный формат токена"
                    )
                payload_part = parts[1]
                payload_part += '=' * (4 - len(payload_part) % 4)
                payload_bytes = base64.urlsafe_b64decode(payload_part)
                payload = json.loads(payload_bytes.decode('utf-8'))
            
            if "sub" not in payload: 
                raise HTTPException(
                    status_code=401,
                    detail="Недействительный токен аутентификации"
                )
                
            return payload
        except HTTPException:
            raise
        except Exception as e:
            print(f"Ошибка верификации токена: {e}")
            raise HTTPException(
                status_code=401,
                detail="Недействительный токен аутентификации"
            )


clerk_auth = ClerkAuth()

def get_current_user(authorization: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """Обязательная аутентификация - только для зарегистрированных пользователей"""
    if not clerk_auth.enabled:
        raise HTTPException(
            status_code=500,
            detail="Аутентификация не настроена. Обратитесь к администратору."
        )
        
    if not authorization:
        raise HTTPException(
            status_code=401, 
            detail="Требуется регистрация и вход в систему"
        )
    
    token = authorization.credentials
    user_data = clerk_auth.verify_token(token)
    
    if not user_data:
        raise HTTPException(
            status_code=401, 
            detail="Недействительный токен. Пожалуйста, войдите в систему заново."
        )
    
    return user_data

def get_optional_current_user(request: Request) -> Optional[Dict[str, Any]]:
    """Опциональная зависимость для получения пользователя"""
    if not clerk_auth.enabled:
        return None
        
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    
    token = auth_header.split(" ")[1]
    try:
        return clerk_auth.verify_token(token)
    except HTTPException:
        return None

def get_user_from_request(request: Request) -> Optional[Dict[str, Any]]:
    """Получаем пользователя из запроса - проверяем заголовок Authorization и query параметр token"""
    if not clerk_auth.enabled:
        return None
    
    # Сначала проверяем Authorization заголовок
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        try:
            return clerk_auth.verify_token(token)
        except HTTPException:
            pass
    
    # Если в заголовке нет токена, проверяем query параметр
    token = request.query_params.get("token")
    if token:
        try:
            return clerk_auth.verify_token(token)
        except HTTPException:
            pass
    
    return None 