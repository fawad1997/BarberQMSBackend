# app/routers/users.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import get_db
from app.core.security import get_password_hash
from app.core.dependencies import get_current_active_user
from typing import List
from app.models import UserRole

router = APIRouter(prefix="/users", tags=["Users"])

@router.post("/", response_model=schemas.UserResponse)
def create_user(user_in: schemas.UserCreate, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(
        (models.User.email == user_in.email) | (models.User.phone_number == user_in.phone_number)
    ).first()
    if user:
        raise HTTPException(
            status_code=400,
            detail="User with this email or phone number already exists",
        )
    hashed_password = get_password_hash(user_in.password)
    new_user = models.User(
        full_name=user_in.full_name,
        email=user_in.email,
        phone_number=user_in.phone_number,
        hashed_password=hashed_password,
        role=UserRole.USER,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@router.get("/me", response_model=schemas.UserResponse)
def read_current_user(current_user: models.User = Depends(get_current_active_user)):
    return current_user


@router.put("/me", response_model=schemas.UserResponse)
def update_current_user(
    user_in: schemas.UserUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    if user_in.password:
        hashed_password = get_password_hash(user_in.password)
        current_user.hashed_password = hashed_password
    if user_in.full_name:
        current_user.full_name = user_in.full_name
    if user_in.email:
        current_user.email = user_in.email
    if user_in.phone_number:
        current_user.phone_number = user_in.phone_number
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return current_user
