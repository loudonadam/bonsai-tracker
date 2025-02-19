# add_table.py
import os
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Create database directory if it doesn't exist
os.makedirs('data', exist_ok=True)

# Use the same database path as in your application
DATABASE_URL = "sqlite:///data/bonsai.db"

# Create the engine
engine = create_engine(DATABASE_URL)

# Create declarative base
Base = declarative_base()

# Define Settings model
class Settings(Base):
    __tablename__ = 'settings'
    
    id = Column(Integer, primary_key=True)
    app_title = Column(String, default="Bonsai Tracker")
    sidebar_image = Column(String)

def main():
    # Create the table
    Base.metadata.create_all(engine)
    
    # Create session
    Session = sessionmaker(bind=engine)
    
    # Create default settings
    with Session() as session:
        # Check if settings already exist
        existing_settings = session.query(Settings).first()
        if not existing_settings:
            default_settings = Settings(
                app_title="Bonsai Tracker",
                sidebar_image="C:\\Users\\loudo\\Desktop\\Bonsai Design\\Screenshot+2020-01-29+at+10.52.32+AM.png"
            )
            session.add(default_settings)
            session.commit()
            print("Created settings table with default values")
        else:
            print("Settings table already exists")

if __name__ == "__main__":
    main()