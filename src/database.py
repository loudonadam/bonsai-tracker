import os
from sqlalchemy import create_engine, Column, Integer, String, Date, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import date

# Ensure data directory exists
os.makedirs('data', exist_ok=True)

# SQLAlchemy setup
Base = declarative_base()
engine = create_engine('sqlite:///data/bonsai.db')
Session = sessionmaker(bind=engine)

class BonsaiTree(Base):
    __tablename__ = 'bonsai_trees'

    id = Column(Integer, primary_key=True)
    tree_number = Column(String, unique=True, nullable=False)
    species = Column(String)
    girth = Column(Integer)  # in mm
    height = Column(Integer)  # in mm
    date_acquired = Column(Date)
    origin_date = Column(Date)
    current_image_path = Column(String)
    special_notes = Column(Text)
    most_recent_report_date = Column(Date)

class TreeUpdate(Base):
    __tablename__ = 'tree_updates'

    id = Column(Integer, primary_key=True)
    tree_id = Column(Integer)
    update_date = Column(Date)
    new_image_path = Column(String)
    girth = Column(Integer)
    notes = Column(Text)

class Reminder(Base):
    __tablename__ = 'reminders'

    id = Column(Integer, primary_key=True)
    tree_id = Column(Integer)
    reminder_date = Column(Date)
    reminder_text = Column(Text)

# Create tables
Base.metadata.create_all(engine)

def get_session():
    """Create and return a database session"""
    return Session()

def add_bonsai_tree(tree_number, species, girth, height, date_acquired, origin_date, image_path=None, special_notes=None):
    """Add a new bonsai tree to the database"""
    session = get_session()
    try:
        new_tree = BonsaiTree(
            tree_number=tree_number,
            species=species,
            girth=girth,
            height=height,
            date_acquired=date_acquired,
            origin_date=origin_date,
            current_image_path=image_path,
            special_notes=special_notes,
            most_recent_report_date=date.today()
        )
        session.add(new_tree)
        session.commit()
        return new_tree.id
    except Exception as e:
        session.rollback()
        print(f"Error adding bonsai tree: {e}")
        return None
    finally:
        session.close()