# app/routers/user_router.py
from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
from app.auth import get_current_user

router = APIRouter(
    prefix="/users",
    tags=["users"],
)

@router.get("/me", response_model=Dict[str, Any])
async def read_users_me(current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Get current user info.
    """
    if not current_user:
        raise HTTPException(status_code=404, detail="User not found")
    return current_user 