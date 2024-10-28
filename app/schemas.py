# app/schemas.py

from pydantic import BaseModel, EmailStr, ConfigDict, field_validator
from typing import Optional
from app.models import AppointmentStatus
from enum import Enum
from datetime import datetime, timezone
import pytz

# At the top of the file, add these imports
TIMEZONE = pytz.timezone('America/Los_Angeles')

# Add these timezone helper functions
def convert_to_pacific(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TIMEZONE)

def validate_timezone(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return convert_to_pacific(dt)

def convert_to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        pacific_dt = TIMEZONE.localize(dt)
    else:
        pacific_dt = dt.astimezone(TIMEZONE)
    return pacific_dt.astimezone(timezone.utc)

class UserRole(str, Enum):
    user = "user"
    shop_owner = "shop_owner"
    barber = "barber"
    admin = "admin"

class UserBase(BaseModel):
    full_name: str
    email: EmailStr
    phone_number: str

class UserCreate(UserBase):
    password: str
    role: Optional[UserRole] = UserRole.user

# Add new schema for shop owner registration
class ShopOwnerRegistration(BaseModel):
    # User details
    full_name: str
    email: EmailStr
    phone_number: str
    password: str

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    password: Optional[str] = None

class UserResponse(UserBase):
    id: int
    is_active: bool
    role: UserRole

    class Config:
        orm_mode = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    user_id: Optional[int] = None

class AppointmentBase(BaseModel):
    shop_id: int
    barber_id: int
    service_id: int
    appointment_time: datetime

    # Add validator for appointment_time
    @field_validator('appointment_time')
    def validate_appointment_time(cls, v):
        return validate_timezone(v)

class AppointmentCreate(AppointmentBase):
    user_id: Optional[int] = None
    full_name: Optional[str] = None
    phone_number: Optional[str] = None

class AppointmentStatusUpdate(BaseModel):
    status: AppointmentStatus

class AppointmentResponse(AppointmentBase):
    id: int
    status: AppointmentStatus
    created_at: datetime

    # Add validator for created_at
    @field_validator('created_at')
    def validate_created_at(cls, v):
        return validate_timezone(v)

    model_config = ConfigDict(from_attributes=True)

class ShopBase(BaseModel):
    name: str
    address: str
    city: str
    state: str
    zip_code: str
    phone_number: Optional[str] = None
    email: Optional[str] = None

class ShopCreate(ShopBase):
    pass

class ShopUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None

class ShopResponse(ShopBase):
    id: int
    owner_id: int

    model_config = ConfigDict(from_attributes=True)

# Add these new schemas after the existing ones
class BarberBase(BaseModel):
    full_name: str
    email: EmailStr
    phone_number: str

class BarberCreate(BarberBase):
    password: str

class BarberUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    status: Optional[str] = None

class BarberResponse(BaseModel):
    id: int
    user_id: int
    shop_id: int
    status: str
    user: UserResponse

    model_config = ConfigDict(from_attributes=True)

class ServiceBase(BaseModel):
    name: str
    duration: int  # Duration in minutes
    price: float
    shop_id: Optional[int] = None

class ServiceCreate(ServiceBase):
    pass

class ServiceUpdate(BaseModel):
    name: Optional[str] = None
    duration: Optional[int] = None
    price: Optional[float] = None

class ServiceResponse(ServiceBase):
    id: int
    shop_id: int

    model_config = ConfigDict(from_attributes=True)

class QueueStatusUpdate(BaseModel):
    status: str

class QueueEntryBase(BaseModel):
    shop_id: int
    user_id: Optional[int] = None
    service_id: int
    full_name: Optional[str] = None
    phone_number: Optional[str] = None

class QueueEntryCreate(QueueEntryBase):
    pass

class QueueEntryResponse(QueueEntryBase):
    id: int
    status: str
    check_in_time: datetime
    service_start_time: Optional[datetime] = None
    service_end_time: Optional[datetime] = None

    # Add validators for all datetime fields
    @field_validator('check_in_time', 'service_start_time', 'service_end_time')
    def validate_times(cls, v):
        if v is not None:
            return validate_timezone(v)
        return v

    model_config = ConfigDict(from_attributes=True)

class DailyReportResponse(BaseModel):
    date: datetime
    total_customers: int
    average_wait_time: float

class FeedbackBase(BaseModel):
    rating: int
    comment: Optional[str] = None
    shop_id: int

class FeedbackCreate(FeedbackBase):
    pass

class FeedbackResponse(FeedbackBase):
    id: int
    user_id: int
    created_at: datetime

    @field_validator('created_at')
    def validate_created_at(cls, v):
        return validate_timezone(v)

    model_config = ConfigDict(from_attributes=True)

class BarberScheduleBase(BaseModel):
    barber_id: int
    day_of_week: int  # 0-6 for Monday-Sunday
    start_time: str   # Format: "HH:MM"
    end_time: str     # Format: "HH:MM"
    is_available: bool = True

class BarberScheduleCreate(BarberScheduleBase):
    pass

class BarberScheduleUpdate(BaseModel):
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    is_available: Optional[bool] = None

class BarberScheduleResponse(BarberScheduleBase):
    id: int
    shop_id: int

    model_config = ConfigDict(from_attributes=True)

# Update login schema
class LoginRequest(BaseModel):
    username: str  # Can be either email or phone number
    password: str
