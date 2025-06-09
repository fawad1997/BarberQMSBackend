## Show file tree

tree -L 4 -a -I 'test_models.py|add_username_migration.py'
or 
Get-TreeWithExclusions -Exclude @("venv", "__pycache__", "*.dist-info", ".git", ".vscode")

## Fixed DB head using
# First, check if any tables exist
psql $DATABASE_URL -c "\dt"

# If tables exist, stamp the database at the latest migration
alembic stamp head

# Then verify
alembic current