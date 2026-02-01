from shared.db import engine, Base
from shared import models

# BE CAREFUL: This script will drop all tables in the database!
# Make sure you have backups if necessary before running this script.
# (venv) c.trillet@dev:~/testdb$ PYTHONPATH=. python shared/drop_all_tables.py

# Drop all tables
Base.metadata.drop_all(bind=engine)
print("All tables dropped successfully.")