# app/models.py

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    Float,
    ForeignKey,
    Text,
    DateTime,
    Date,
    Time,
    Enum,
    Table,
    UniqueConstraint,
    ARRAY,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum
from datetime import datetime, timedelta


# Enums for user roles
class UserRole(enum.Enum):
    USER = "USER"
    SHOP_OWNER = "SHOP_OWNER"
    BARBER = "BARBER"
    ADMIN = "ADMIN"


# Enums for appointment and queue statuses
class AppointmentStatus(enum.Enum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class QueueStatus(enum.Enum):
    ARRIVED = "ARRIVED"
    CHECKED_IN = "CHECKED_IN"
    IN_SERVICE = "IN_SERVICE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


# Enum for employee status (formerly BarberStatus)
class EmployeeStatus(enum.Enum):
    AVAILABLE = "available"
    IN_SERVICE = "in_service"
    ON_BREAK = "on_break"
    OFF = "off"

# Alias for backward compatibility
BarberStatus = EmployeeStatus


# Enum for schedule types
class ScheduleType(enum.Enum):
    WORKING = "working"
    BREAK = "break"
    OFF = "off"


# Enum for override types
class OverrideType(enum.Enum):
    HOLIDAY = "holiday"
    SPECIAL_EVENT = "special_event"
    EMERGENCY = "emergency"
    PERSONAL = "personal"
    SICK_LEAVE = "sick_leave"


# Association table for many-to-many relationship between Employees and Services
employee_services = Table(
    "employee_services",
    Base.metadata,
    Column("employee_id", Integer, ForeignKey("employees.id"), primary_key=True),
    Column("service_id", Integer, ForeignKey("services.id"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    phone_number = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    role = Column(Enum(UserRole), default=UserRole.USER)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_first_login = Column(Boolean, default=True)  # Track first-time login
    
    # Password reset fields
    reset_token = Column(String, nullable=True, index=True)
    reset_token_expires = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    businesses = relationship("Business", back_populates="owner", cascade="all, delete")
    shops = relationship("Shop", back_populates="owner", cascade="all, delete")
    employee_profile = relationship(
        "Employee", uselist=False, back_populates="user", cascade="all, delete"
    )
    feedbacks = relationship("Feedback", back_populates="user", cascade="all, delete")
    appointments = relationship(
        "Appointment", back_populates="user", cascade="all, delete"
    )
    queue_entries = relationship(
        "QueueEntry", back_populates="user", cascade="all, delete"
    )


class Business(Base):
    __tablename__ = "businesses"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=False, index=True)
    username = Column(String, unique=True, nullable=True, index=True)
    address = Column(String, nullable=False)
    city = Column(String, nullable=False)
    state = Column(String, nullable=False)
    zip_code = Column(String, nullable=False)
    phone_number = Column(String, nullable=True)
    email = Column(String, nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    average_wait_time = Column(Float, default=0.0)
    is_open_24_hours = Column(Boolean, default=False)
    
    # New fields
    description = Column(Text, nullable=True)
    logo_url = Column(String, nullable=True)

    # Relationships
    owner = relationship("User", back_populates="businesses")
    employees = relationship(
        "Employee", back_populates="business", cascade="all, delete-orphan"
    )
    services = relationship(
        "Service", back_populates="business", cascade="all, delete-orphan"
    )
    queue_entries = relationship(
        "QueueEntry", back_populates="business", cascade="all, delete-orphan"
    )
    appointments = relationship(
        "Appointment", back_populates="business", cascade="all, delete-orphan"
    )
    feedbacks = relationship(
        "Feedback", back_populates="business", cascade="all, delete-orphan"
    )
    operating_hours = relationship(
        "BusinessOperatingHours", back_populates="business", cascade="all, delete-orphan"
    )
    schedule_overrides = relationship("ScheduleOverride", back_populates="business", cascade="all, delete-orphan")
    advertisements = relationship("BusinessAdvertisement", back_populates="business", cascade="all, delete-orphan")


class BusinessOperatingHours(Base):
    __tablename__ = "business_operating_hours"
    
    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=False)
    day_of_week = Column(Integer, nullable=False)  # 0=Sunday, 1=Monday, ..., 6=Saturday
    opening_time = Column(Time, nullable=True)  # Null if closed that day
    closing_time = Column(Time, nullable=True)  # Null if closed that day
    is_closed = Column(Boolean, default=False)
    
    # New lunch break fields
    lunch_break_start = Column(Time, nullable=True)
    lunch_break_end = Column(Time, nullable=True)
    
    # Relationship
    business = relationship("Business", back_populates="operating_hours")
    
    __table_args__ = (
        UniqueConstraint('business_id', 'day_of_week', name='uix_business_day'),
    )


class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=False)
    status = Column(Enum(EmployeeStatus), default=EmployeeStatus.AVAILABLE)

    # Relationships
    user = relationship("User", back_populates="employee_profile")
    business = relationship("Business", back_populates="employees")
    services = relationship(
        "Service", secondary=employee_services, back_populates="employees"
    )
    appointments = relationship(
        "Appointment", back_populates="employee", cascade="all, delete-orphan"
    )
    feedbacks = relationship(
        "Feedback", back_populates="employee", cascade="all, delete-orphan"
    )
    schedules = relationship(
        "EmployeeSchedule", back_populates="employee", cascade="all, delete-orphan"
    )
    schedule_overrides = relationship("ScheduleOverride", back_populates="employee", cascade="all, delete-orphan")


class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    duration = Column(Integer, nullable=False)  # Duration in minutes
    price = Column(Float, nullable=False)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=False)
    
    # New fields
    is_active = Column(Boolean, default=True)
    category = Column(String, nullable=True)

    # Relationships
    business = relationship("Business", back_populates="services")
    employees = relationship(
        "Employee", secondary=employee_services, back_populates="services"
    )
    appointments = relationship(
        "Appointment", back_populates="service", cascade="all, delete-orphan"
    )
    queue_entries = relationship(
        "QueueEntry", back_populates="service", cascade="all, delete-orphan"
    )


class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    service_id = Column(Integer, ForeignKey("services.id"), nullable=True)
    appointment_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    status = Column(Enum(AppointmentStatus), default=AppointmentStatus.SCHEDULED)
    created_at = Column(DateTime, default=func.now())
    actual_start_time = Column(DateTime, nullable=True)
    actual_end_time = Column(DateTime, nullable=True)
    full_name = Column(String, nullable=True)
    phone_number = Column(String, nullable=True, index=True)
    number_of_people = Column(Integer, default=1)
    custom_duration = Column(Integer, nullable=True)  # In minutes, overrides service duration
    custom_price = Column(Float, nullable=True)  # Overrides default service price
    
    # New fields
    total_duration = Column(Integer, nullable=True)  # Calculated from services
    total_price = Column(Float, nullable=True)  # Calculated from services
    notes = Column(Text, nullable=True)  # Special instructions

    # Relationships
    user = relationship("User", back_populates="appointments")
    business = relationship("Business", back_populates="appointments")
    employee = relationship("Employee", back_populates="appointments")
    service = relationship("Service", back_populates="appointments")

    def __init__(self, **kwargs):
        if 'end_time' not in kwargs and 'appointment_time' in kwargs:
            # If end_time is not provided but appointment_time is, calculate end_time
            service_duration = 30  # Default duration in minutes
            if 'service_id' in kwargs and kwargs['service_id']:
                from sqlalchemy.orm import Session
                from app.database import SessionLocal
                db = SessionLocal()
                service = db.query(Service).filter(Service.id == kwargs['service_id']).first()
                if service:
                    service_duration = service.duration
                db.close()
            kwargs['end_time'] = kwargs['appointment_time'] + timedelta(minutes=service_duration)
        
        super().__init__(**kwargs)
        if self.user_id is None and (not self.phone_number or not self.full_name):
            raise ValueError("Either user_id or both phone_number and full_name must be provided")


class Feedback(Base):
    __tablename__ = "feedbacks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    rating = Column(Integer, nullable=False)  # Rating between 1 and 5
    message = Column(Text, nullable=True)  # Renamed from comments
    subject = Column(String, nullable=True)  # New field
    category = Column(String, nullable=True)  # Service, wait time, cleanliness, etc.
    created_at = Column(DateTime, default=func.now())

    # Relationships
    user = relationship("User", back_populates="feedbacks")
    business = relationship("Business", back_populates="feedbacks")
    employee = relationship("Employee", back_populates="feedbacks")


class QueueEntry(Base):
    __tablename__ = "queue_entries"

    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=False)
    service_id = Column(Integer, ForeignKey("services.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    full_name = Column(String, nullable=False)
    phone_number = Column(String, nullable=False)
    number_of_people = Column(Integer, default=1)
    status = Column(Enum(QueueStatus), default=QueueStatus.CHECKED_IN)
    position_in_queue = Column(Integer)
    check_in_time = Column(DateTime, default=func.now())
    arrival_confirmed = Column(Boolean, default=False)
    service_start_time = Column(DateTime, nullable=True)
    service_end_time = Column(DateTime, nullable=True)
    custom_duration = Column(Integer, nullable=True)  # In minutes, overrides service duration
    custom_price = Column(Float, nullable=True)  # Overrides default service price
    
    # New fields
    estimated_service_time = Column(DateTime, nullable=True)  # When service is expected to start
    notes = Column(Text, nullable=True)  # Special instructions

    # Relationships
    business = relationship("Business", back_populates="queue_entries")
    service = relationship("Service", back_populates="queue_entries")
    user = relationship("User", back_populates="queue_entries")
    employee = relationship("Employee")


class ScheduleRepeatFrequency(enum.Enum):
    NONE = "NONE"
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    YEARLY = "YEARLY"

    @classmethod
    def _missing_(cls, value):
        if value is None:
            return cls.NONE
        if isinstance(value, str):
            try:
                return cls[value.upper()]
            except KeyError:
                return cls.NONE
        return cls.NONE


class EmployeeSchedule(Base):
    __tablename__ = "employee_schedules"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    day_of_week = Column(Integer, nullable=False)  # 0-6 for Sunday-Saturday
    start_time = Column(Time, nullable=True)  # Daily start time
    end_time = Column(Time, nullable=True)  # Daily end time
    lunch_break_start = Column(Time, nullable=True)  # Personal lunch break
    lunch_break_end = Column(Time, nullable=True)  # Personal lunch break
    is_working = Column(Boolean, default=True)  # Whether working that day
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    employee = relationship("Employee", back_populates="schedules")

    @property
    def business_id(self):
        return self.employee.business_id

    __table_args__ = (
        UniqueConstraint('employee_id', 'day_of_week', name='uix_employee_day'),
    )


class ScheduleOverride(Base):
    __tablename__ = "schedule_overrides"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=False)
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=True)
    repeat_frequency = Column(
        Enum(ScheduleRepeatFrequency, name="schedulerepeatfrequency", create_constraint=False),
        nullable=False,
        server_default="NONE"
    )
    
    # New fields
    reason = Column(String, nullable=True)  # Why the override exists
    override_type = Column(Enum(OverrideType), nullable=True)  # Type of override

    # Relationships
    employee = relationship("Employee", back_populates="schedule_overrides")
    business = relationship("Business", back_populates="schedule_overrides")


class BusinessAdvertisement(Base):
    __tablename__ = "business_advertisements"

    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=False)
    image_url = Column(String, nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())

    # Relationship
    business = relationship("Business", back_populates="advertisements")


class Shop(Base):
    __tablename__ = "shops"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=False, index=True)
    username = Column(String, unique=True, nullable=True, index=True)
    address = Column(String, nullable=False)
    city = Column(String, nullable=False)
    state = Column(String, nullable=False)
    zip_code = Column(String, nullable=False)
    phone_number = Column(String, nullable=True)
    email = Column(String, nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    average_wait_time = Column(Float, default=0.0)
    has_advertisement = Column(Boolean, default=False)
    advertisement_image_url = Column(String, nullable=True)
    advertisement_start_date = Column(DateTime, nullable=True)
    advertisement_end_date = Column(DateTime, nullable=True)
    is_advertisement_active = Column(Boolean, default=False)
    opening_time = Column(Time, nullable=True)
    closing_time = Column(Time, nullable=True)
    is_open_24_hours = Column(Boolean, default=False)
    timezone = Column(String, nullable=False, default="America/Los_Angeles")

    # Relationships
    owner = relationship("User", back_populates="shops")
    operating_hours = relationship(
        "ShopOperatingHours", back_populates="shop", cascade="all, delete-orphan"
    )


class ShopOperatingHours(Base):
    __tablename__ = "shop_operating_hours"
    
    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False)
    day_of_week = Column(Integer, nullable=False)  # 0=Sunday, 1=Monday, ..., 6=Saturday
    opening_time = Column(Time, nullable=True)  # Null if closed that day
    closing_time = Column(Time, nullable=True)  # Null if closed that day
    is_closed = Column(Boolean, default=False)
    
    # Lunch break fields
    lunch_break_start = Column(Time, nullable=True)
    lunch_break_end = Column(Time, nullable=True)
    
    # Relationship
    shop = relationship("Shop", back_populates="operating_hours")
    
    __table_args__ = (
        UniqueConstraint('shop_id', 'day_of_week', name='uix_shop_day'),
    )


class ContactMessage(Base):
    __tablename__ = "contact_messages"

    id = Column(Integer, primary_key=True, index=True)
    subject = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    email = Column(String, nullable=True)
    phone_number = Column(String, nullable=True)
    created_at = Column(DateTime, default=func.now())
