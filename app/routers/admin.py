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

@router.get("/shops/", response_model=List[schemas.ShopResponse])
def get_all_shops(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin)
):
    shops = db.query(models.Shop).all()
    return shops

@router.put("/shops/{shop_id}/approve", response_model=schemas.ShopResponse)
def approve_shop(
    shop_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin)
):
    shop = db.query(models.Shop).filter(models.Shop.id == shop_id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    shop.is_approved = True
    db.add(shop)
    db.commit()
    db.refresh(shop)
    return shop

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
