# app/schemas.py

from pydantic import BaseModel, EmailStr, ConfigDict, computed_field, field_validator, Field
from typing import Optional, List
from app.models import AppointmentStatus, BarberStatus, QueueStatus
from enum import Enum
from datetime import datetime, timezone, time
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
    user = "USER"
    shop_owner = "SHOP_OWNER"
    barber = "BARBER"
    admin = "ADMIN"

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
    created_at: datetime

    @field_validator('created_at')
    def validate_created_at(cls, v):
        return validate_timezone(v)

    model_config = ConfigDict(from_attributes=True)

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    user_id: Optional[int] = None

class AppointmentBase(BaseModel):
    shop_id: int
    barber_id: Optional[int] = None
    service_id: Optional[int] = None
    appointment_time: datetime
    number_of_people: Optional[int] = Field(default=1, ge=1)

    @field_validator('appointment_time')
    def validate_appointment_time(cls, v):
        return validate_timezone(v)

class AppointmentCreate(AppointmentBase):
    user_id: Optional[int] = None
    full_name: Optional[str] = None
    phone_number: Optional[str] = None

    @field_validator('full_name', 'phone_number')
    def validate_guest_fields(cls, v, info):
        # Skip validation if field is not provided
        if info.data.get('user_id') is not None:
            return v
        # For guest users, both fields are required
        if v is None:
            raise ValueError("full_name and phone_number are required for guest users")
        return v

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
    id: int
    name: str
    address: str
    city: str
    state: str
    zip_code: str
    phone_number: Optional[str] = None
    email: Optional[str] = None
    opening_time: time
    closing_time: time
    average_wait_time: Optional[float] = None
    has_advertisement: Optional[bool] = False
    advertisement_image_url: Optional[str] = None
    advertisement_start_date: Optional[datetime] = None
    advertisement_end_date: Optional[datetime] = None
    is_advertisement_active: Optional[bool] = False
    estimated_wait_time: Optional[int] = None
    is_open: Optional[bool] = None
    formatted_hours: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class ShopCreate(BaseModel):
    name: str
    address: str
    city: str
    state: str
    zip_code: str
    phone_number: Optional[str] = None
    email: Optional[str] = None
    opening_time: time
    closing_time: time
    average_wait_time: Optional[float] = 0.0

    model_config = ConfigDict(from_attributes=True)

class ShopUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None
    opening_time: Optional[time] = None
    closing_time: Optional[time] = None
    average_wait_time: Optional[float] = None
    has_advertisement: Optional[bool] = None
    advertisement_image_url: Optional[str] = None
    advertisement_start_date: Optional[datetime] = None
    advertisement_end_date: Optional[datetime] = None
    is_advertisement_active: Optional[bool] = None

    # Add validator for dates
    @field_validator('advertisement_start_date', 'advertisement_end_date')
    def validate_dates(cls, v):
        if v is not None:
            return validate_timezone(v)
        return v

    model_config = ConfigDict(from_attributes=True)

class ShopResponse(ShopBase):
    id: int
    owner_id: int

    model_config = ConfigDict(from_attributes=True)

# First define ServiceBase and ServiceResponse
class ServiceBase(BaseModel):
    name: str
    duration: int
    price: float

class ServiceCreate(ServiceBase):
    pass

class ServiceUpdate(ServiceBase):
    pass

class ServiceResponse(ServiceBase):
    id: int
    shop_id: int

    model_config = ConfigDict(from_attributes=True)

# Then define BarberResponse which uses ServiceResponse
class BarberResponse(BaseModel):
    id: int
    user_id: int
    shop_id: int
    status: BarberStatus
    full_name: str
    email: str
    phone_number: str
    is_active: bool
    services: List[ServiceResponse] = []

    model_config = ConfigDict(from_attributes=True)

class BarberBase(BaseModel):
    full_name: str
    email: EmailStr
    phone_number: str

class BarberCreate(BaseModel):
    full_name: str
    email: EmailStr
    phone_number: str
    password: Optional[str] = "Temp1234"
    status: Optional[BarberStatus] = BarberStatus.AVAILABLE

class BarberUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    status: Optional[BarberStatus] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


class BarberScheduleBase(BaseModel):
    barber_id: int
    day_of_week: int = Field(
        ..., 
        ge=0, 
        le=6, 
        description="0=Sunday, 1=Monday, ..., 6=Saturday"
    )
    start_time: time   # Changed from str to time
    end_time: time     # Changed from str to time

class BarberScheduleCreate(BarberScheduleBase):
    # Removed field validators as Pydantic handles time parsing
    pass

class BarberScheduleUpdate(BaseModel):
    day_of_week: Optional[int] = Field(
        None, 
        ge=0, 
        le=6, 
        description="0=Sunday, 1=Monday, ..., 6=Saturday"
    )
    start_time: Optional[time] = None
    end_time: Optional[time] = None

class BarberScheduleResponse(BaseModel):
    id: int
    barber_id: int
    shop_id: int
    day_of_week: int
    start_time: time   # Format handled by Pydantic
    end_time: time     # Format handled by Pydantic

    class Config:
        from_attributes = True  # Enables ORM mode for Pydantic

    @classmethod
    def from_orm_with_shop(cls, obj):
        return cls(
            id=obj.id,
            barber_id=obj.barber_id,
            shop_id=obj.barber.shop_id,  # Access shop_id through the barber relationship
            day_of_week=obj.day_of_week,
            start_time=obj.start_time,
            end_time=obj.end_time
        )


# Update login schema
class LoginRequest(BaseModel):
    username: str  # Can be either email or phone number
    password: str

# Add a new response schema for listing shops
class ShopListResponse(BaseModel):
    items: List[ShopBase]
    total: int
    page: int
    pages: int

    model_config = ConfigDict(from_attributes=True)

class AdvertisementUpdate(BaseModel):
    has_advertisement: bool
    advertisement_image_url: Optional[str] = None
    advertisement_start_date: Optional[datetime] = None
    advertisement_end_date: Optional[datetime] = None
    is_advertisement_active: Optional[bool] = None

    @field_validator('advertisement_start_date', 'advertisement_end_date')
    def validate_dates(cls, v):
        if v is not None:
            return validate_timezone(v)
        return v

class TokenWithUserDetails(Token):
    user_id: int
    full_name: str
    email: EmailStr
    phone_number: str
    role: UserRole
    is_active: bool
    created_at: datetime

    @field_validator('created_at')
    def validate_created_at(cls, v):
        return validate_timezone(v)

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

class ShopDetailedBarberSchedule(BarberScheduleResponse):
    day_name: str = ""

    @computed_field
    def formatted_time(self) -> str:
        return f"{self.start_time.strftime('%I:%M %p')} - {self.end_time.strftime('%I:%M %p')}"

class ShopDetailedBarber(BarberResponse):
    schedules: List[ShopDetailedBarberSchedule] = []
    services: List[ServiceResponse] = []

class ShopDetailedResponse(ShopResponse):
    barbers: List[ShopDetailedBarber] = []
    services: List[ServiceResponse] = []
    estimated_wait_time: Optional[int] = None
    is_open: bool = False
    formatted_hours: str = ""

    model_config = ConfigDict(from_attributes=True)


class QueueEntryCreatePublic(BaseModel):
    shop_id: int
    service_id: Optional[int] = None
    barber_id: Optional[int] = None
    full_name: str
    phone_number: str
    number_of_people: int = Field(default=1, ge=1)

class QueueEntryPublicResponse(BaseModel):
    id: int
    position_in_queue: int
    full_name: str
    status: QueueStatus
    check_in_time: datetime
    service_start_time: Optional[datetime] = None
    number_of_people: int
    barber_id: Optional[int] = None
    service_id: Optional[int] = None

    @field_validator('check_in_time', 'service_start_time')
    def validate_times(cls, v):
        if v is not None:
            return validate_timezone(v)
        return v

    model_config = ConfigDict(from_attributes=True)
