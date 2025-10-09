# app/routers/auth.py
from fastapi import APIRouter

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)

# This is a placeholder for any future auth-related endpoints.
# For now, Clerk handles most of the auth flow on the frontend. 