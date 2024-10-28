# app/routers/auth.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import get_db
from app.core.security import verify_password, create_access_token, get_password_hash
from app.core.dependencies import oauth2_scheme
from datetime import timedelta
import os

router = APIRouter(prefix="/auth", tags=["Authentication"])

ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

@router.post("/register/shop-owner", response_model=schemas.UserResponse)
async def register_shop_owner(
    registration: schemas.ShopOwnerRegistration,
    db: Session = Depends(get_db)
):
    # Check if user exists with email or phone
    existing_user = db.query(models.User).filter(
        (models.User.email == registration.email) |
        (models.User.phone_number == registration.phone_number)
    ).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email or phone number already exists"
        )

    # Create user with shop owner role
    db_user = models.User(
        full_name=registration.full_name,
        email=registration.email,
        phone_number=registration.phone_number,
        hashed_password=get_password_hash(registration.password),
        role=models.UserRole.SHOP_OWNER
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    return db_user

@router.post("/login", response_model=schemas.Token)
async def login_for_access_token(
    form_data: schemas.LoginRequest,
    db: Session = Depends(get_db)
):
    # Check if user exists with either email or phone number
    user = db.query(models.User).filter(
        (models.User.email == form_data.username) |
        (models.User.phone_number == form_data.username)
    ).first()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}
