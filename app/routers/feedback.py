# app/routers/feedback.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app import models, schemas
from app.database import get_db
from app.core.dependencies import get_current_active_user

router = APIRouter(prefix="/feedback", tags=["Feedback"])

@router.post("/", response_model=schemas.FeedbackResponse)
def create_feedback(
    feedback_in: schemas.FeedbackCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    appointment = db.query(models.Appointment).filter(
        models.Appointment.id == feedback_in.appointment_id,
        models.Appointment.user_id == current_user.id
    ).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found or not associated with current user")

    new_feedback = models.Feedback(
        appointment_id=feedback_in.appointment_id,
        user_id=current_user.id,
        barber_id=appointment.barber_id,
        rating=feedback_in.rating,
        comment=feedback_in.comment
    )
    db.add(new_feedback)
    db.commit()
    db.refresh(new_feedback)
    return new_feedback

@router.get("/", response_model=List[schemas.FeedbackResponse])
def get_feedbacks(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    feedbacks = db.query(models.Feedback).filter(
        models.Feedback.user_id == current_user.id
    ).all()
    return feedbacks
