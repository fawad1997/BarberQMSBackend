# app/routers/queue.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
from app import models, schemas
from app.database import get_db
from app.core.dependencies import get_current_active_user

router = APIRouter(prefix="/queue", tags=["Queue"])

@router.post("/", response_model=schemas.QueueEntryResponse)
def join_queue(
    shop_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    shop = db.query(models.Shop).filter(models.Shop.id == shop_id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    existing_entry = db.query(models.QueueEntry).filter(
        models.QueueEntry.shop_id == shop_id,
        models.QueueEntry.user_id == current_user.id
    ).first()
    if existing_entry:
        raise HTTPException(status_code=400, detail="Already in queue")

    position = db.query(models.QueueEntry).filter(
        models.QueueEntry.shop_id == shop_id
    ).count() + 1

    new_entry = models.QueueEntry(
        shop_id=shop_id,
        user_id=current_user.id,
        position=position,
        joined_at=datetime.utcnow()
    )
    db.add(new_entry)
    db.commit()
    db.refresh(new_entry)
    return new_entry

@router.get("/", response_model=List[schemas.QueueEntryResponse])
def get_queue_position(
    shop_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    entries = db.query(models.QueueEntry).filter(
        models.QueueEntry.shop_id == shop_id
    ).order_by(models.QueueEntry.position.asc()).all()
    return entries
