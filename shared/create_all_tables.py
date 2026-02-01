from shared.db import engine, Base
from shared import models  # Ensure all models are imported

# (venv) c.trillet@dev:~/testdb$ PYTHONPATH=. python shared/create_all_tables.py 

# Create all tables
Base.metadata.create_all(bind=engine)
print("All tables created successfully.")