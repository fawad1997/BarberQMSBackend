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
    # Verify business exists
    business = db.query(models.Business).filter(models.Business.id == feedback_in.business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    
    # Verify employee exists if provided
    if feedback_in.employee_id:
        employee = db.query(models.Employee).filter(
            models.Employee.id == feedback_in.employee_id,
            models.Employee.business_id == feedback_in.business_id
        ).first()
        if not employee:
            raise HTTPException(status_code=404, detail="Employee not found in this business")

    new_feedback = models.Feedback(
        user_id=current_user.id,
        business_id=feedback_in.business_id,
        employee_id=feedback_in.employee_id,
        rating=feedback_in.rating,
        message=feedback_in.message,
        subject=feedback_in.subject,
        category=feedback_in.category
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
