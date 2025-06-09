## Show file tree

tree -L 4 -a -I 'test_models.py|add_username_migration.py'
or 
Get-TreeWithExclusions -Exclude @("venv", "__pycache__", "*.dist-info", ".git", ".vscode")