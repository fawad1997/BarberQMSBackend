# app/routers/users.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app import models, schemas
from app.database import get_db
from app.core.security import get_password_hash, verify_password
from app.core.dependencies import get_current_active_user
from typing import List, Optional
from app.models import UserRole
from pydantic import BaseModel

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

# Profile update request model
class ProfileUpdateRequest(BaseModel):
    name: Optional[str] = None
    current_password: Optional[str] = None
    new_password: Optional[str] = None

# Add profile update endpoint
@router.put("/profile", response_model=dict)
async def update_user_profile(
    request: ProfileUpdateRequest,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    # Get the current user from the database
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Check if this is a password update request
    if request.current_password and request.new_password:
        # Verify current password
        if not verify_password(request.current_password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Current password is incorrect"
            )
        
        # Password policy check
        if len(request.new_password) < 8:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="New password must be at least 8 characters long"
            )
        
        # Update password
        user.hashed_password = get_password_hash(request.new_password)
    
    # Name update
    if request.name:
        # Validate name
        if len(request.name) < 2:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Name must be at least 2 characters long"
            )
        
        # Update name in both user and current_user objects
        user.full_name = request.name
        current_user.full_name = request.name
    
    # Save changes
    db.commit()
    db.refresh(user)
    
    # Return updated user info with additional fields to help frontend
    return {
        "id": user.id,
        "name": user.full_name,
        "email": user.email,
        "updated": True
    }
