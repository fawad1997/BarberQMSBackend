# test_models.py

from app.database import Base, engine, get_db
from app import models
from sqlalchemy.orm import Session

# Ensure tables are created
Base.metadata.create_all(bind=engine)

# Create a new database session
db: Session = Session(bind=engine)

# Test creating a user
new_user = models.User(
    full_name="Test User",
    email="test@example.com",
    phone_number="1234567890",
    hashed_password="hashedpassword",
    role=models.UserRole.USER,
)

db.add(new_user)
db.commit()
db.refresh(new_user)

print(f"Created user: {new_user.id} - {new_user.full_name}")

db.close()
