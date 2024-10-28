# app/routers/unregistered_users.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app import models, schemas
from datetime import timedelta
from app.core.security import create_access_token
from app.database import get_db
from typing import List
import random

router = APIRouter(prefix="/unregistered-users", tags=["Unregistered Users"])

verification_codes = {}

@router.post("/request-code")
def request_verification_code(phone_number: str):
    # Generate a random 6-digit code
    code = random.randint(100000, 999999)
    # Store it in a dictionary with the phone number as the key
    verification_codes[phone_number] = code
    # Send the code via SMS (integration with SMS gateway required)
    # For demonstration, we'll just print it
    print(f"Verification code for {phone_number}: {code}")
    return {"message": "Verification code sent"}

@router.post("/verify-code")
def verify_code(phone_number: str, code: int):
    stored_code = verification_codes.get(phone_number)
    if stored_code != code:
        raise HTTPException(status_code=400, detail="Invalid verification code")
    # Generate a temporary token
    access_token_expires = timedelta(minutes=15)
    access_token = create_access_token(
        data={"sub": phone_number}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


from app.core.dependencies import get_current_unregistered_user

@router.get("/appointments", response_model=List[schemas.AppointmentResponse])
def get_appointments(
    current_phone_number: str = Depends(get_current_unregistered_user),
    db: Session = Depends(get_db)
):
    appointments = db.query(models.Appointment).filter(
        models.Appointment.phone_number == current_phone_number
    ).all()
    return appointments