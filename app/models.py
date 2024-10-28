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
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum


# Enums for user roles
class UserRole(enum.Enum):
    USER = "user"
    SHOP_OWNER = "shop_owner"
    BARBER = "barber"
    ADMIN = "admin"


# Enums for appointment and queue statuses
class AppointmentStatus(enum.Enum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class QueueStatus(enum.Enum):
    CHECKED_IN = "checked_in"
    ARRIVED = "arrived"
    IN_SERVICE = "in_service"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


# Enum for barber status
class BarberStatus(enum.Enum):
    AVAILABLE = "available"
    IN_SERVICE = "in_service"
    ON_BREAK = "on_break"
    OFF = "off"


# Enum for schedule types
class ScheduleType(enum.Enum):
    WORKING = "working"
    BREAK = "break"
    OFF = "off"


# Association table for many-to-many relationship between Barbers and Services
barber_services = Table(
    "barber_services",
    Base.metadata,
    Column("barber_id", Integer, ForeignKey("barbers.id"), primary_key=True),
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

    # Relationships
    shops = relationship("Shop", back_populates="owner", cascade="all, delete")
    barber_profile = relationship(
        "Barber", uselist=False, back_populates="user", cascade="all, delete"
    )
    feedbacks = relationship("Feedback", back_populates="user", cascade="all, delete")
    appointments = relationship(
        "Appointment", back_populates="user", cascade="all, delete"
    )
    queue_entries = relationship(
        "QueueEntry", back_populates="user", cascade="all, delete"
    )


class Shop(Base):
    __tablename__ = "shops"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    location = Column(String, nullable=False)
    operating_hours = Column(String)  # JSON or structured format
    average_wait_time = Column(Float, default=0.0)

    # Relationships
    owner = relationship("User", back_populates="shops")
    barbers = relationship(
        "Barber", back_populates="shop", cascade="all, delete-orphan"
    )
    services = relationship(
        "Service", back_populates="shop", cascade="all, delete-orphan"
    )
    queue_entries = relationship(
        "QueueEntry", back_populates="shop", cascade="all, delete-orphan"
    )
    appointments = relationship(
        "Appointment", back_populates="shop", cascade="all, delete-orphan"
    )
    feedbacks = relationship(
        "Feedback", back_populates="shop", cascade="all, delete-orphan"
    )


class Barber(Base):
    __tablename__ = "barbers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False)
    status = Column(Enum(BarberStatus), default=BarberStatus.AVAILABLE)

    # Relationships
    user = relationship("User", back_populates="barber_profile")
    shop = relationship("Shop", back_populates="barbers")
    services = relationship(
        "Service", secondary=barber_services, back_populates="barbers"
    )
    appointments = relationship(
        "Appointment", back_populates="barber", cascade="all, delete-orphan"
    )
    feedbacks = relationship(
        "Feedback", back_populates="barber", cascade="all, delete-orphan"
    )
    schedules = relationship(
        "BarberSchedule", back_populates="barber", cascade="all, delete-orphan"
    )


class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    duration = Column(Integer, nullable=False)  # Duration in minutes
    price = Column(Float, nullable=False)
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False)

    # Relationships
    shop = relationship("Shop", back_populates="services")
    barbers = relationship(
        "Barber", secondary=barber_services, back_populates="services"
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
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Made nullable
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False)
    barber_id = Column(Integer, ForeignKey("barbers.id"), nullable=False)
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False)
    appointment_time = Column(DateTime, nullable=False)
    status = Column(Enum(AppointmentStatus), default=AppointmentStatus.SCHEDULED)
    created_at = Column(DateTime, default=func.now())
    actual_start_time = Column(DateTime, nullable=True)
    actual_end_time = Column(DateTime, nullable=True)

    # Added fields for unregistered users
    full_name = Column(String, nullable=True)
    phone_number = Column(String, nullable=True, index=True)

    # Relationships
    user = relationship("User", back_populates="appointments")
    shop = relationship("Shop", back_populates="appointments")
    barber = relationship("Barber", back_populates="appointments")
    service = relationship("Service", back_populates="appointments")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.user_id is None and (not self.phone_number or not self.full_name):
            raise ValueError("Either user_id or both phone_number and full_name must be provided")


class Feedback(Base):
    __tablename__ = "feedbacks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=True)
    barber_id = Column(Integer, ForeignKey("barbers.id"), nullable=True)
    rating = Column(Integer, nullable=False)  # Rating between 1 and 5
    comments = Column(Text, nullable=True)
    category = Column(String, nullable=True)  # Service, wait time, cleanliness, etc.
    created_at = Column(DateTime, default=func.now())

    # Relationships
    user = relationship("User", back_populates="feedbacks")
    shop = relationship("Shop", back_populates="feedbacks")
    barber = relationship("Barber", back_populates="feedbacks")


class QueueEntry(Base):
    __tablename__ = "queue_entries"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False)
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    barber_id = Column(Integer, ForeignKey("barbers.id"), nullable=True)
    full_name = Column(String, nullable=False)
    phone_number = Column(String, nullable=False)
    number_of_people = Column(Integer, default=1)
    status = Column(Enum(QueueStatus), default=QueueStatus.CHECKED_IN)
    position_in_queue = Column(Integer)
    check_in_time = Column(DateTime, default=func.now())
    arrival_confirmed = Column(Boolean, default=False)
    service_start_time = Column(DateTime, nullable=True)
    service_end_time = Column(DateTime, nullable=True)

    # Relationships
    shop = relationship("Shop", back_populates="queue_entries")
    service = relationship("Service", back_populates="queue_entries")
    user = relationship("User", back_populates="queue_entries")
    barber = relationship("Barber")


class BarberSchedule(Base):
    __tablename__ = "barber_schedules"

    id = Column(Integer, primary_key=True, index=True)
    barber_id = Column(Integer, ForeignKey("barbers.id"), nullable=False)
    date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    schedule_type = Column(Enum(ScheduleType), default=ScheduleType.WORKING)
    is_available = Column(Boolean, default=True)

    # Relationships
    barber = relationship("Barber", back_populates="schedules")