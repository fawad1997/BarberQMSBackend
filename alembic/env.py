# alembic/env.py
import os
import sys
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# this is the Alembic Config object, which provides access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
fileConfig(config.config_file_name)

# Set up your project's base directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import your models' metadata object here
from app.database import Base
from app import models  # Ensure all models are imported

target_metadata = Base.metadata

# Set the SQLAlchemy URL from environment variables
config.set_main_option('sqlalchemy.url', os.getenv('DATABASE_URL'))