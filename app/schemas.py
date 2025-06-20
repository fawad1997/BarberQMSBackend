# app/schemas.py

from pydantic import BaseModel, EmailStr, ConfigDict, computed_field, field_validator, Field
from typing import Optional, List
from datetime import datetime, timezone, time, timedelta, date
from app.models import AppointmentStatus, BarberStatus, QueueStatus, ScheduleRepeatFrequency
from enum import Enum
import pytz
import re

# At the top of the file, add these imports
TIMEZONE = pytz.timezone('America/Los_Angeles')
UTC = pytz.UTC

# Add these timezone helper functions
def convert_to_pacific(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = UTC.localize(dt)
    return dt.astimezone(TIMEZONE)

def validate_timezone(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = UTC.localize(dt)
    return convert_to_pacific(dt)

def convert_to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        pacific_dt = TIMEZONE.localize(dt)
    else:
        pacific_dt = dt.astimezone(TIMEZONE)
    return pacific_dt.astimezone(UTC)

def generate_slug(name: str) -> str:
    """Generate a URL-friendly slug from a string"""
    # Convert to lowercase and replace spaces with hyphens
    slug = name.lower().replace(' ', '-')
    # Remove special characters
    slug = re.sub(r'[^a-z0-9-]', '', slug)
    # Remove duplicate hyphens
    slug = re.sub(r'-+', '-', slug)
    # Remove leading/trailing hyphens
    slug = slug.strip('-')
    return slug

# Reserved usernames that cannot be used by shops
RESERVED_USERNAMES = {
    "my-shop", "barbershop", "barber-shop", "my-barber-shop",
    "admin", "api", "www", "mail", "ftp", "localhost", "test",
    "support", "help", "contact", "about", "privacy", "terms",
    "login", "register", "signup", "dashboard", "profile", "settings"
}

def validate_username(username: str) -> str:
    """Validate and format username according to business rules"""
    if not username:
        raise ValueError("Username cannot be empty")
    
    # Convert to lowercase and clean
    username = username.lower().strip()
    
    # Check length (minimum 3, maximum 30 characters)
    if len(username) < 3:
        raise ValueError("Username must be at least 3 characters long")
    if len(username) > 30:
        raise ValueError("Username must be no more than 30 characters long")
    
    # Check for valid characters (alphanumeric, hyphens, underscores)
    if not re.match(r'^[a-z0-9-_]+$', username):
        raise ValueError("Username can only contain lowercase letters, numbers, hyphens, and underscores")
    
    # Check if it starts or ends with special characters
    if username.startswith(('-', '_')) or username.endswith(('-', '_')):
        raise ValueError("Username cannot start or end with hyphens or underscores")
    
    # Check against reserved usernames
    if username in RESERVED_USERNAMES:
        raise ValueError(f"Username '{username}' is reserved and cannot be used")
    
    return username

def is_username_available(username: str, db, exclude_shop_id: Optional[int] = None) -> bool:
    """Check if username is available (not taken by another shop)"""
    from app import models
    
    query = db.query(models.Shop).filter(models.Shop.username == username)
    if exclude_shop_id:
        query = query.filter(models.Shop.id != exclude_shop_id)
    
    return query.first() is None

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
    is_first_login: bool

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
    end_time: Optional[datetime] = None
    number_of_people: Optional[int] = Field(default=1, ge=1)

    @field_validator('appointment_time', 'end_time')
    def validate_times(cls, v, info):
        if v is not None:
            v = validate_timezone(v)
            if info.field_name == 'end_time' and 'appointment_time' in info.data:
                appointment_time = info.data['appointment_time']
                if v <= appointment_time:
                    raise ValueError("End time must be after appointment time")
        return v

    model_config = ConfigDict(from_attributes=True)

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

    @field_validator('end_time')
    def validate_end_time(cls, v, info):
        if v is None and 'appointment_time' in info.data and 'service_id' in info.data:
            # If end_time is not provided, calculate it based on service duration
            from app.database import SessionLocal
            from app.models import Service
            db = SessionLocal()
            try:
                service = db.query(Service).filter(Service.id == info.data['service_id']).first()
                if service:
                    duration = service.duration
                else:
                    duration = 30  # Default duration if service not found
            finally:
                db.close()
            return info.data['appointment_time'] + timedelta(minutes=duration)
        return v

class AppointmentStatusUpdate(BaseModel):
    status: AppointmentStatus

class AppointmentResponse(AppointmentBase):
    id: int
    status: AppointmentStatus
    created_at: datetime
    actual_start_time: Optional[datetime] = None
    actual_end_time: Optional[datetime] = None
    full_name: Optional[str] = None
    phone_number: Optional[str] = None

    # Add validator for all datetime fields
    @field_validator('created_at', 'actual_start_time', 'actual_end_time', 'end_time')
    def validate_times(cls, v):
        if v is not None:
            return validate_timezone(v)
        return v

    model_config = ConfigDict(from_attributes=True)

class ShopOperatingHoursBase(BaseModel):
    day_of_week: int = Field(..., ge=0, le=6, description="0=Sunday, 1=Monday, ..., 6=Saturday")
    opening_time: Optional[time] = None
    closing_time: Optional[time] = None
    is_closed: bool = False

class ShopOperatingHoursCreate(ShopOperatingHoursBase):
    pass

class ShopOperatingHoursResponse(ShopOperatingHoursBase):
    id: int
    shop_id: int
    
    model_config = ConfigDict(from_attributes=True)
    
    @computed_field
    def day_name(self) -> str:
        days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
        return days[self.day_of_week]
    
    @computed_field
    def formatted_hours(self) -> str:
        if self.is_closed:
            return "Closed"
        if not self.opening_time or not self.closing_time:
            return "Closed"
        return f"{self.opening_time.strftime('%I:%M %p')} - {self.closing_time.strftime('%I:%M %p')}"

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
    slug: str
    username: str  # Username is now required

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
    operating_hours: Optional[List[ShopOperatingHoursCreate]] = None
    slug: Optional[str] = None
    username: str  # Username is now required

    @field_validator('username')
    def validate_username_field(cls, v):
        return validate_username(v)

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
    slug: Optional[str] = None
    username: Optional[str] = None

    @field_validator('username')
    def validate_username_field(cls, v):
        if v is not None:
            return validate_username(v)
        return v

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
    operating_hours: List[ShopOperatingHoursResponse] = []

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

class BarberProfileResponse(BaseModel):
    id: int
    user_id: int
    shop_id: int
    full_name: str
    email: str
    phone_number: str
    shop: dict

    model_config = ConfigDict(from_attributes=True)

class BarberBase(BaseModel):
    full_name: str
    email: EmailStr
    phone_number: str

class BarberCreate(BaseModel):
    full_name: str
    email: EmailStr
    phone_number: str
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
    start_date: datetime
    end_date: datetime
    repeat_frequency: ScheduleRepeatFrequency = ScheduleRepeatFrequency.NONE

    @field_validator("repeat_frequency", mode="before")
    def validate_repeat_frequency(cls, v):
        if v is None:
            return ScheduleRepeatFrequency.NONE
        if isinstance(v, str):
            try:
                return ScheduleRepeatFrequency[v.upper()]
            except KeyError:
                return ScheduleRepeatFrequency.NONE
        return v

    @field_validator("start_date", "end_date")
    def validate_dates(cls, v):
        if v.tzinfo is None:
            v = UTC.localize(v)
        return v.astimezone(TIMEZONE)

    @field_validator("end_date")
    def validate_end_date(cls, v, info):
        if "start_date" in info.data:
            start_date = info.data["start_date"]
            if v <= start_date:
                raise ValueError("End date must be after start date")
        return v

    model_config = ConfigDict(from_attributes=True)

class BarberScheduleCreate(BarberScheduleBase):
    pass

class BarberScheduleUpdate(BaseModel):
    start_date: datetime | None = None
    end_date: datetime | None = None
    repeat_frequency: ScheduleRepeatFrequency | None = None

    @field_validator("repeat_frequency", mode="before")
    def validate_repeat_frequency(cls, v):
        if v is None:
            return ScheduleRepeatFrequency.NONE
        if isinstance(v, str):
            try:
                return ScheduleRepeatFrequency[v.upper()]
            except KeyError:
                return ScheduleRepeatFrequency.NONE
        return v

    @field_validator("start_date", "end_date")
    def validate_dates(cls, v):
        if v is not None and v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v

    model_config = ConfigDict(from_attributes=True)

class BarberSchedule(BarberScheduleBase):
    id: int
    created_at: datetime
    updated_at: datetime

    @field_validator('created_at', 'updated_at')
    def validate_timestamps(cls, v):
        if v is not None:
            # Convert to UTC if timezone-naive
            if v.tzinfo is None:
                v = timezone.utc.localize(v)
            else:
                v = v.astimezone(timezone.utc)
        return v

    class Config:
        from_attributes = True

class BarberScheduleResponse(BaseModel):
    id: int
    barber_id: int
    start_date: datetime
    end_date: datetime
    repeat_frequency: ScheduleRepeatFrequency
    created_at: datetime
    updated_at: datetime

    @field_validator('start_date', 'end_date', 'created_at', 'updated_at')
    def validate_dates(cls, v):
        if v is not None:
            # Convert to UTC if timezone-naive
            if v.tzinfo is None:
                v = UTC.localize(v)
            # Convert to Pacific time for response
            return v.astimezone(TIMEZONE)
        return v

    model_config = ConfigDict(from_attributes=True)

# Keep the old response schema for backward compatibility
class BarberScheduleResponseLegacy(BaseModel):
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
    is_first_login: bool

    @field_validator('created_at')
    def validate_created_at(cls, v):
        return validate_timezone(v)

    model_config = ConfigDict(from_attributes=True)

class QueueStatusUpdate(BaseModel):
    status: QueueStatus

class QueueBarberUpdate(BaseModel):
    barber_id: int

class QueueServiceUpdate(BaseModel):
    service_id: int

class QueueEntryBase(BaseModel):
    shop_id: int
    user_id: Optional[int] = None
    service_id: Optional[int] = None
    full_name: Optional[str] = None
    phone_number: Optional[str] = None

class QueueEntryCreate(QueueEntryBase):
    pass

class ServiceInfo(BaseModel):
    id: int
    name: str
    duration: int
    price: float

    model_config = ConfigDict(from_attributes=True)

class BarberInfo(BaseModel):
    id: int
    status: BarberStatus
    full_name: str
    phone_number: Optional[str] = None
    email: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

class QueueEntryResponse(QueueEntryBase):
    id: int
    status: QueueStatus
    position_in_queue: int
    check_in_time: datetime
    service_start_time: Optional[datetime] = None
    service_end_time: Optional[datetime] = None
    barber_id: Optional[int] = None
    number_of_people: int = 1
    barber: Optional[BarberInfo] = None
    service: Optional[ServiceInfo] = None

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
    @computed_field
    def formatted_time(self) -> str:
        # Convert times to Pacific timezone for display
        start = self.start_date
        end = self.end_date
        
        # Ensure times are in Pacific timezone
        if start.tzinfo is None:
            start = TIMEZONE.localize(start)
        if end.tzinfo is None:
            end = TIMEZONE.localize(end)
        
        return f"{start.strftime('%I:%M %p')} - {end.strftime('%I:%M %p')}"

    @computed_field
    def day_name(self) -> str:
        # Get the day name from the start date
        return self.start_date.strftime('%A')

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

def validate_timezone(dt: datetime) -> datetime:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TIMEZONE)

class QueueEntryPublicResponse(BaseModel):
    shop_id: int
    id: int
    position_in_queue: int
    full_name: str
    status: QueueStatus
    check_in_time: datetime
    service_start_time: Optional[datetime] = None
    number_of_people: int
    barber_id: Optional[int] = None
    service_id: Optional[int] = None
    estimated_wait_time: Optional[int] = None  # <-- New Field in minutes

    @field_validator('check_in_time', 'service_start_time', mode='before')
    def validate_times(cls, v):
        if v is None:
            return None
        return validate_timezone(v)


    model_config = ConfigDict(from_attributes=True)


class QueueReorderItem(BaseModel):
    queue_id: int
    new_position: int

class QueueReorderRequest(BaseModel):
    reordered_entries: List[QueueReorderItem]

class DetailedAppointmentResponse(AppointmentResponse):
    barber: Optional[BarberInfo] = None
    service: Optional[ServiceInfo] = None
    
    @computed_field
    def duration_minutes(self) -> int:
        if self.end_time and self.appointment_time:
            # Convert both to UTC, assuming naive datetimes are in local time
            end = self.end_time.astimezone(timezone.utc) if self.end_time.tzinfo else self.end_time.replace(tzinfo=timezone.utc)
            start = self.appointment_time.astimezone(timezone.utc) if self.appointment_time.tzinfo else self.appointment_time.replace(tzinfo=timezone.utc)
            return int((end - start).total_seconds() / 60)
        return 30  # Default duration
    model_config = ConfigDict(from_attributes=True)

class DisplayQueueItem(BaseModel):
    id: int
    shop_id: int
    shop_name: str
    display_id: str  # W1, A2, etc.
    name: str
    type: str  # "Walk-in" or "Appointment"
    service: str
    position: int  # Original position (in walk-ins or appointments)
    calculated_position: int  # Overall position in combined queue
    estimated_duration: int  # in minutes
    estimated_time: Optional[datetime] = None
    number_of_people: int = 1

    @field_validator('estimated_time')
    def validate_estimated_time(cls, v):
        if v is not None:
            return validate_timezone(v)
        return v

class SimplifiedQueueResponse(BaseModel):
    shop_id: int
    shop_name: str
    current_time: str
    queue: List[dict] = []

class AppointmentUpdate(BaseModel):
    appointment_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    barber_id: Optional[int] = None
    service_id: Optional[int] = None
    number_of_people: Optional[int] = Field(default=None, ge=1)
    full_name: Optional[str] = None
    phone_number: Optional[str] = None

    @field_validator('appointment_time')
    def validate_appointment_time(cls, v):
        if v:
            return validate_timezone(v)
        return v
    
    @field_validator('end_time')
    def validate_end_time(cls, v):
        if v:
            return validate_timezone(v)
        return v

    @field_validator('full_name', 'phone_number')
    def validate_guest_fields(cls, v, info):
        # Allow updating individual fields
        return v

class ScheduleBreakBase(BaseModel):
    break_start: Optional[time] = None
    break_end: Optional[time] = None

class ScheduleBreakCreate(ScheduleBreakBase):
    pass

class ScheduleBreakResponse(ScheduleBreakBase):
    id: int
    work_schedule_id: int

    model_config = ConfigDict(from_attributes=True)

class WorkScheduleBase(BaseModel):
    name: Optional[str] = None
    day_of_week: Optional[List[int]] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    effective_start_date: Optional[date] = None
    effective_end_date: Optional[date] = None

class WorkScheduleCreate(WorkScheduleBase):
    shop_id: int
    breaks: Optional[List[ScheduleBreakCreate]] = None

class WorkScheduleResponse(WorkScheduleBase):
    id: int
    shop_id: int
    breaks: List[ScheduleBreakResponse] = []

    model_config = ConfigDict(from_attributes=True)

class EmployeeScheduleBase(BaseModel):
    employee_id: int
    work_schedule_id: int

class EmployeeScheduleCreate(EmployeeScheduleBase):
    pass

class EmployeeScheduleResponse(EmployeeScheduleBase):
    model_config = ConfigDict(from_attributes=True)

class ScheduleOverrideBase(BaseModel):
    barber_id: Optional[int] = None
    shop_id: int
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    repeat_frequency: ScheduleRepeatFrequency = ScheduleRepeatFrequency.NONE

    @field_validator("repeat_frequency", mode="before")
    def validate_repeat_frequency(cls, v):
        if v is None:
            return ScheduleRepeatFrequency.NONE
        if isinstance(v, str):
            try:
                return ScheduleRepeatFrequency[v.upper()]
            except KeyError:
                return ScheduleRepeatFrequency.NONE
        return v

    @field_validator("start_date", "end_date")
    def validate_dates(cls, v):
        if v is not None and v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v

    @field_validator("end_date")
    def validate_end_date(cls, v, info):
        if v is not None and "start_date" in info.data and info.data["start_date"] is not None:
            start_date = info.data["start_date"]
            if v <= start_date:
                raise ValueError("End date must be after start date")
        return v

    model_config = ConfigDict(from_attributes=True)

class ScheduleOverrideCreate(ScheduleOverrideBase):
    pass

class ScheduleOverrideResponse(ScheduleOverrideBase):
    id: int

    model_config = ConfigDict(from_attributes=True)

# Password Reset Schemas
class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ForgotPasswordResponse(BaseModel):
    success: bool
    message: str

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8, description="Password must be at least 8 characters long")

class ResetPasswordResponse(BaseModel):
    success: bool
    message: str

class ValidateResetTokenRequest(BaseModel):
    token: str

class ValidateResetTokenResponse(BaseModel):
    valid: bool
    message: str
    user_email: Optional[str] = None

# Username availability response schema
class UsernameAvailabilityResponse(BaseModel):
    username: str
    available: bool
    message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

# Barber metrics schemas
class DailyMetric(BaseModel):
    date: str
    customers_served: int

class BarberMetrics(BaseModel):
    time_period: str
    start_date: str
    end_date: str
    customers_served: int
    avg_service_duration_minutes: int
    daily_data: List[DailyMetric]
