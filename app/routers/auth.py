# app/routers/auth.py

from fastapi import APIRouter, Depends, HTTPException, status, Form
from sqlalchemy.orm import Session
from app import models, schemas
from app.schemas import TIMEZONE, convert_to_utc
from app.database import get_db
from app.core.security import verify_password, create_access_token, get_password_hash
from app.core.dependencies import oauth2_scheme
from datetime import timedelta, datetime
import os
from pytz import timezone
from fastapi.security import OAuth2PasswordRequestForm
import logging

# Initialize logger
logger = logging.getLogger(__name__)
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
    pacific_now = convert_to_utc(datetime.now(TIMEZONE))
    db_user = models.User(
        full_name=registration.full_name,
        email=registration.email,
        phone_number=registration.phone_number,
        hashed_password=get_password_hash(registration.password),
        role=models.UserRole.SHOP_OWNER,
        created_at=pacific_now
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    return db_user

@router.post("/login", response_model=schemas.TokenWithUserDetails)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(
        (models.User.email == form_data.username) |
        (models.User.phone_number == form_data.username)
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    logger.debug(f"Login attempt for user: ID={user.id}, Role={user.role}")
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "phone_number": user.phone_number,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at
    }
