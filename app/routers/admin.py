# app/routers/admin.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app import models, schemas
from app.database import get_db
from app.core.dependencies import get_current_user_by_role
from app.models import UserRole

router = APIRouter(prefix="/admin", tags=["Admin"])

get_current_admin = get_current_user_by_role(UserRole.ADMIN)

@router.get("/businesses/", response_model=List[schemas.BusinessResponse])
def get_all_businesses(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin)
):
    businesses = db.query(models.Business).all()
    return businesses

@router.get("/users/", response_model=List[schemas.UserResponse])
def get_all_users(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin)
):
    users = db.query(models.User).all()
    return users

@router.put("/users/{user_id}/deactivate", response_model=schemas.UserResponse)
def deactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin)
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = False
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

@router.delete("/businesses/{business_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_business(
    business_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin)
):
    business = db.query(models.Business).filter(models.Business.id == business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    
    db.delete(business)
    db.commit()
    return
