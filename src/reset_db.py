# create_settings_table.py
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from src.database import engine

# Create the engine
engine = create_engine(engine)

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
    
    # Create default settings
    from sqlalchemy.orm import Session
    with Session(engine) as session:
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