from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_admin
from app.models import AdminUser
from app.schemas import LoginIn, TokenOut
from app.security import create_access_token, verify_secret

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_db)) -> TokenOut:
    user = db.scalar(select(AdminUser).where(AdminUser.email == payload.email.lower()))
    if not user or not verify_secret(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Identifiants invalides")
    return TokenOut(access_token=create_access_token(str(user.id)))


@router.get("/me")
def me(user: AdminUser = Depends(current_admin)) -> dict:
    return {"id": str(user.id), "email": user.email}
