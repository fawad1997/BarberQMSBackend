Remove-Item alembic/versions/* -Recurse -Force

# Initialize fresh migrations
alembic init alembic

# Create new migration
alembic revision --autogenerate -m "initial"

# Run migration
alembic upgrade head