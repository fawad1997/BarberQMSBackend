# app/schemas.py

from pydantic import BaseModel, EmailStr, ConfigDict, computed_field, field_validator, Field
from typing import Optional, List
from datetime import datetime, timezone, time, timedelta, date
from app.models import AppointmentStatus, EmployeeStatus, QueueStatus, ScheduleRepeatFrequency, OverrideType
from enum import Enum
import pytz
import re

# At the top of the file, add these imports
TIMEZONE = pytz.timezone('America/Los_Angeles')
UTC = pytz.UTC

# US Timezones mapping
US_TIMEZONES = {
    "America/New_York": "Eastern Time (GMT-5/-4)",
    "America/Chicago": "Central Time (GMT-6/-5)", 
    "America/Denver": "Mountain Time (GMT-7/-6)",
    "America/Phoenix": "Mountain Standard Time (GMT-7)",
    "America/Los_Angeles": "Pacific Time (GMT-8/-7)",
    "America/Anchorage": "Alaska Time (GMT-9/-8)",
    "Pacific/Honolulu": "Hawaii Time (GMT-10)"
}

def validate_us_timezone(timezone_str: str) -> str:
    """Validate that the timezone is a supported US timezone."""
    if timezone_str not in US_TIMEZONES:
        raise ValueError(f"Timezone must be one of: {', '.join(US_TIMEZONES.keys())}")
    return timezone_str

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

# Reserved usernames that cannot be used by businesses
RESERVED_USERNAMES = {
    "my-business", "barbershop", "barber-shop", "my-barber-shop",
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

def is_username_available(username: str, db, exclude_business_id: Optional[int] = None) -> bool:
    """Check if username is available (not taken by another business)"""
    from app import models
    
    query = db.query(models.Business).filter(models.Business.username == username)
    if exclude_business_id:
        query = query.filter(models.Business.id != exclude_business_id)
    
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
    business_id: int
    employee_id: Optional[int] = None
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
    notes: Optional[str] = None

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
    total_duration: Optional[int] = None
    total_price: Optional[float] = None
    notes: Optional[str] = None

    # Add validator for all datetime fields
    @field_validator('created_at', 'actual_start_time', 'actual_end_time', 'end_time')
    def validate_times(cls, v):
        if v is not None:
            return validate_timezone(v)
        return v

    model_config = ConfigDict(from_attributes=True)

class BusinessOperatingHoursBase(BaseModel):
    day_of_week: int = Field(..., ge=0, le=6, description="0=Sunday, 1=Monday, ..., 6=Saturday")
    opening_time: Optional[time] = None
    closing_time: Optional[time] = None
    is_closed: bool = False
    lunch_break_start: Optional[time] = None
    lunch_break_end: Optional[time] = None

class BusinessOperatingHoursCreate(BusinessOperatingHoursBase):
    pass

class BusinessOperatingHoursResponse(BusinessOperatingHoursBase):
    id: int
    business_id: int
    
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

class BusinessBase(BaseModel):
    id: int
    name: str
    address: str
    city: str
    state: str
    zip_code: str
    phone_number: Optional[str] = None
    email: Optional[str] = None
    average_wait_time: Optional[float] = None
    estimated_wait_time: Optional[int] = None
    is_open: Optional[bool] = None
    formatted_hours: Optional[str] = None
    slug: str
    username: str  # Username is now required
    description: Optional[str] = None
    logo_url: Optional[str] = None
    is_open_24_hours: Optional[bool] = False

    model_config = ConfigDict(from_attributes=True)

class BusinessCreate(BaseModel):
    name: str
    address: str
    city: str
    state: str
    zip_code: str
    phone_number: Optional[str] = None
    email: Optional[str] = None
    average_wait_time: Optional[float] = 0.0
    operating_hours: Optional[List[BusinessOperatingHoursCreate]] = None
    slug: Optional[str] = None
    username: str  # Username is now required
    description: Optional[str] = None
    logo_url: Optional[str] = None

    @field_validator('username')
    def validate_username_field(cls, v):
        return validate_username(v)

    model_config = ConfigDict(from_attributes=True)

class BusinessUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None
    average_wait_time: Optional[float] = None
    slug: Optional[str] = None
    username: Optional[str] = None
    description: Optional[str] = None
    logo_url: Optional[str] = None

    @field_validator('username')
    def validate_username_field(cls, v):
        if v is not None:
            return validate_username(v)
        return v

    model_config = ConfigDict(from_attributes=True)

class BusinessResponse(BusinessBase):
    id: int
    owner_id: int
    operating_hours: List[BusinessOperatingHoursResponse] = []

    model_config = ConfigDict(from_attributes=True)

# First define ServiceBase and ServiceResponse
class ServiceBase(BaseModel):
    name: str
    duration: int
    price: float
    is_active: Optional[bool] = True
    category: Optional[str] = None

class ServiceCreate(ServiceBase):
    pass

class ServiceUpdate(ServiceBase):
    pass

class ServiceResponse(ServiceBase):
    id: int
    business_id: int

    model_config = ConfigDict(from_attributes=True)

# Then define EmployeeResponse which uses ServiceResponse
class EmployeeResponse(BaseModel):
    id: int
    user_id: int
    business_id: int
    status: EmployeeStatus
    full_name: str
    email: str
    phone_number: str
    is_active: bool
    services: List[ServiceResponse] = []

    model_config = ConfigDict(from_attributes=True)

class EmployeeProfileResponse(BaseModel):
    id: int
    user_id: int
    business_id: int
    full_name: str
    email: str
    phone_number: str
    business: dict

    model_config = ConfigDict(from_attributes=True)

class EmployeeBase(BaseModel):
    full_name: str
    email: EmailStr
    phone_number: str

class EmployeeCreate(BaseModel):
    full_name: str
    email: EmailStr
    phone_number: str
    status: Optional[EmployeeStatus] = EmployeeStatus.AVAILABLE

class EmployeeUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    status: Optional[EmployeeStatus] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None

class EmployeeScheduleBase(BaseModel):
    employee_id: int
    day_of_week: int = Field(..., ge=0, le=6, description="0=Sunday, 1=Monday, ..., 6=Saturday")
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    lunch_break_start: Optional[time] = None
    lunch_break_end: Optional[time] = None
    is_working: bool = True

    @field_validator("day_of_week")
    def validate_day_of_week(cls, v):
        if v < 0 or v > 6:
            raise ValueError("day_of_week must be between 0 (Sunday) and 6 (Saturday)")
        return v

    model_config = ConfigDict(from_attributes=True)

class EmployeeScheduleCreate(EmployeeScheduleBase):
    pass

class EmployeeScheduleUpdate(BaseModel):
    day_of_week: Optional[int] = Field(None, ge=0, le=6)
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    lunch_break_start: Optional[time] = None
    lunch_break_end: Optional[time] = None
    is_working: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True)

class EmployeeScheduleResponse(EmployeeScheduleBase):
    id: int
    created_at: datetime
    updated_at: datetime

    @field_validator('created_at', 'updated_at')
    def validate_dates(cls, v):
        if v is not None:
            # Convert to UTC if timezone-naive
            if v.tzinfo is None:
                v = UTC.localize(v)
            # Convert to Pacific time for response
            return v.astimezone(TIMEZONE)
        return v

    @computed_field
    def day_name(self) -> str:
        days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
        return days[self.day_of_week]

    @computed_field
    def formatted_time(self) -> str:
        if not self.is_working or not self.start_time or not self.end_time:
            return "Not Working"
        return f"{self.start_time.strftime('%I:%M %p')} - {self.end_time.strftime('%I:%M %p')}"

    model_config = ConfigDict(from_attributes=True)

# Update login schema
class LoginRequest(BaseModel):
    username: str  # Can be either email or phone number
    password: str

# Add a new response schema for listing businesses
class BusinessListResponse(BaseModel):
    items: List[BusinessBase]
    total: int
    page: int
    pages: int

    model_config = ConfigDict(from_attributes=True)

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

class QueueEmployeeUpdate(BaseModel):
    employee_id: int

class QueueServiceUpdate(BaseModel):
    service_id: int

class QueueEntryBase(BaseModel):
    business_id: int
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

class EmployeeInfo(BaseModel):
    id: int
    status: EmployeeStatus
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
    estimated_service_time: Optional[datetime] = None
    employee_id: Optional[int] = None
    number_of_people: int = 1
    notes: Optional[str] = None
    employee: Optional[EmployeeInfo] = None
    service: Optional[ServiceInfo] = None

    # Add validators for all datetime fields
    @field_validator('check_in_time', 'service_start_time', 'service_end_time', 'estimated_service_time')
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
    message: Optional[str] = None  # Renamed from comment
    subject: Optional[str] = None
    business_id: int

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

class BusinessDetailedEmployeeSchedule(EmployeeScheduleResponse):
    pass

class BusinessDetailedEmployee(EmployeeResponse):
    schedules: List[BusinessDetailedEmployeeSchedule] = []
    services: List[ServiceResponse] = []

class BusinessDetailedResponse(BusinessResponse):
    employees: List[BusinessDetailedEmployee] = []
    services: List[ServiceResponse] = []
    estimated_wait_time: Optional[int] = None
    is_open: bool = False
    formatted_hours: str = ""

    model_config = ConfigDict(from_attributes=True)

class QueueEntryCreatePublic(BaseModel):
    business_id: int
    service_id: Optional[int] = None
    employee_id: Optional[int] = None
    full_name: str
    phone_number: str
    number_of_people: int = Field(default=1, ge=1)
    notes: Optional[str] = None

class QueueEntryPublicResponse(BaseModel):
    business_id: int
    id: int
    position_in_queue: int
    full_name: str
    status: QueueStatus
    check_in_time: datetime
    service_start_time: Optional[datetime] = None
    estimated_service_time: Optional[datetime] = None
    number_of_people: int
    employee_id: Optional[int] = None
    service_id: Optional[int] = None
    estimated_wait_time: Optional[int] = None  # <-- New Field in minutes
    notes: Optional[str] = None

    @field_validator('check_in_time', 'service_start_time', 'estimated_service_time', mode='before')
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
    employee: Optional[EmployeeInfo] = None
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
    business_id: int
    business_name: str
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
    business_id: int
    business_name: str
    current_time: str
    queue: List[dict] = []

class AppointmentUpdate(BaseModel):
    appointment_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    employee_id: Optional[int] = None
    service_id: Optional[int] = None
    number_of_people: Optional[int] = Field(default=None, ge=1)
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    notes: Optional[str] = None

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

class ScheduleOverrideBase(BaseModel):
    employee_id: Optional[int] = None
    business_id: int
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    repeat_frequency: ScheduleRepeatFrequency = ScheduleRepeatFrequency.NONE
    reason: Optional[str] = None
    override_type: Optional[OverrideType] = None

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

# Employee metrics schemas
class DailyMetric(BaseModel):
    date: str
    customers_served: int

class EmployeeMetrics(BaseModel):
    time_period: str
    start_date: str
    end_date: str
    customers_served: int
    avg_service_duration_minutes: int
    daily_data: List[DailyMetric]

# Business Advertisement schemas
class BusinessAdvertisementBase(BaseModel):
    business_id: int
    image_url: str
    start_date: datetime
    end_date: datetime
    is_active: bool = True

class BusinessAdvertisementCreate(BusinessAdvertisementBase):
    pass

class BusinessAdvertisementResponse(BusinessAdvertisementBase):
    id: int
    created_at: datetime

    @field_validator('start_date', 'end_date', 'created_at')
    def validate_dates(cls, v):
        if v is not None:
            return validate_timezone(v)
        return v

    model_config = ConfigDict(from_attributes=True)

# Contact Message schemas
class ContactMessageCreate(BaseModel):
    subject: str
    message: str
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None

class ContactMessageResponse(BaseModel):
    id: int
    subject: str
    message: str
    email: Optional[str] = None
    phone_number: Optional[str] = None
    created_at: datetime

    @field_validator('created_at')
    def validate_created_at(cls, v):
        return validate_timezone(v)

    model_config = ConfigDict(from_attributes=True)
