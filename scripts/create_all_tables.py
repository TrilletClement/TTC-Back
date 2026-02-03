from app.orm_models.db import engine, Base
from app.orm_models import models  # Ensure all models are imported

# Create all tables
Base.metadata.create_all(bind=engine)
print("All tables created successfully.")
