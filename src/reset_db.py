# src/reset_db.py
from src.models import Base
from src.database import engine

def reset_database():
    """Drop all tables and recreate them"""
    print("Dropping all tables...")
    Base.metadata.drop_all(engine)
    
    print("Creating new tables...")
    Base.metadata.create_all(engine)
    
    print("Database reset complete!")

if __name__ == "__main__":
    reset_database()