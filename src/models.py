# src/models.py
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class Species(Base):
    __tablename__ = 'species'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship to trees
    trees = relationship("Tree", back_populates="species_info")

class Tree(Base):
    __tablename__ = 'trees'
    
    id = Column(Integer, primary_key=True)
    tree_number = Column(String(50), unique=True, nullable=False)
    tree_name = Column(String(50), unique=True, nullable=False)
    species_id = Column(Integer, ForeignKey('species.id'), nullable=False)
    date_acquired = Column(DateTime, nullable=False)
    origin_date = Column(DateTime, nullable=False)  # Used for calculating true age
    current_girth = Column(Float)  # in cm
    notes = Column(Text)
    is_archived = Column(Integer, default=0)  # 0 = active, 1 = archived
    
    
    # Relationships
    species_info = relationship("Species", back_populates="trees")
    updates = relationship("TreeUpdate", back_populates="tree", cascade="all, delete-orphan")
    photos = relationship("Photo", back_populates="tree", cascade="all, delete-orphan")
    reminders = relationship("Reminder", back_populates="tree", cascade="all, delete-orphan")
    
    @property
    def training_age(self):
        """Calculate years in training based on acquisition date"""
        return (datetime.now() - self.date_acquired).days / 365.25
    
    @property
    def true_age(self):
        """Calculate true age based on origin date"""
        return (datetime.now() - self.origin_date).days / 365.25

# Keep existing TreeUpdate, Photo, and Reminder models...

class TreeUpdate(Base):
    __tablename__ = 'tree_updates'
    
    id = Column(Integer, primary_key=True)
    tree_id = Column(Integer, ForeignKey('trees.id'), nullable=False)
    update_date = Column(DateTime, default=datetime.utcnow, nullable=False)
    girth = Column(Float)  # in cm
    work_performed = Column(Text, nullable=False)
    
    # Relationships
    tree = relationship("Tree", back_populates="updates")

class Photo(Base):
    __tablename__ = 'photos'
    
    id = Column(Integer, primary_key=True)
    tree_id = Column(Integer, ForeignKey('trees.id'), nullable=False)
    file_path = Column(String(255), nullable=False)
    photo_date = Column(DateTime, nullable=False)  # Date photo was taken
    upload_date = Column(DateTime, default=datetime.utcnow, nullable=False)
    description = Column(Text)
    is_starred = Column(Integer, default=0)  # New column: 0 = not starred, 1 = starred
    
    # Relationships
    tree = relationship("Tree", back_populates="photos")

class Reminder(Base):
    __tablename__ = 'reminders'
    
    id = Column(Integer, primary_key=True)
    tree_id = Column(Integer, ForeignKey('trees.id'), nullable=False)
    reminder_date = Column(DateTime, nullable=False)
    message = Column(Text, nullable=False)
    is_completed = Column(Integer, default=0)  # 0 = pending, 1 = completed
    notification_sent = Column(Integer, default=0)
    created_date = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    tree = relationship("Tree", back_populates="reminders")