# src/migrate_db.py
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from models import Base, Tree, Species, TreeUpdate, Photo, Reminder
import shutil
from datetime import datetime

# Get the database path
DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data'))
DB_PATH = os.path.join(DATA_DIR, 'bonsai.db')
BACKUP_PATH = os.path.join(DATA_DIR, 'bonsai_backup.db')

def backup_database():
    """Create a backup of the existing database"""
    if os.path.exists(DB_PATH):
        shutil.copy2(DB_PATH, BACKUP_PATH)
        print(f"Backup created at {BACKUP_PATH}")

def migrate_database():
    """Perform the database migration"""
    # Create backup first
    backup_database()
    
    # Connect to existing database
    old_engine = create_engine(f'sqlite:///{DB_PATH}')
    OldSession = sessionmaker(bind=old_engine)
    old_session = OldSession()
    
    try:
        # Read all existing data using only the columns we know exist
        trees_data = []
        for t in old_session.query(Tree).all():
            tree_dict = {
                'id': t.id,
                'tree_number': t.tree_number,
                'species_id': t.species_id,
                'date_acquired': t.date_acquired,
                'origin_date': t.origin_date,
                'current_girth': t.current_girth,
                'notes': t.notes
            }
            trees_data.append(tree_dict)
        
        species_data = [
            {
                'id': s.id,
                'name': s.name,
                'created_at': s.created_at
            } for s in old_session.query(Species).all()
        ]
        
        updates_data = [
            {
                'id': u.id,
                'tree_id': u.tree_id,
                'update_date': u.update_date,
                'girth': u.girth,
                'work_performed': u.work_performed
            } for u in old_session.query(TreeUpdate).all()
        ]
        
        photos_data = [
            {
                'id': p.id,
                'tree_id': p.tree_id,
                'file_path': p.file_path,
                'photo_date': p.photo_date,
                'upload_date': p.upload_date,
                'description': p.description
            } for p in old_session.query(Photo).all()
        ]
        
        reminders_data = [
            {
                'id': r.id,
                'tree_id': r.tree_id,
                'reminder_date': r.reminder_date,
                'message': r.message,
                'is_completed': r.is_completed,
                'created_date': r.created_date
            } for r in old_session.query(Reminder).all()
        ]
        
        # Close old session
        old_session.close()
        
        # Remove old database
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
        
        # Create new database with updated schema
        new_engine = create_engine(f'sqlite:///{DB_PATH}')
        Base.metadata.create_all(new_engine)
        
        # Create new session
        NewSession = sessionmaker(bind=new_engine)
        new_session = NewSession()
        
        # Restore data
        for species in species_data:
            new_session.add(Species(**species))
        new_session.commit()  # Commit species first
        
        for tree in trees_data:
            new_session.add(Tree(**tree))
        new_session.commit()  # Commit trees next
        
        for update in updates_data:
            new_session.add(TreeUpdate(**update))
        
        for photo in photos_data:
            new_session.add(Photo(**photo))
        
        for reminder in reminders_data:
            new_session.add(Reminder(**reminder))
        
        # Final commit
        new_session.commit()
        print("Migration completed successfully!")
        
    except Exception as e:
        print(f"Error during migration: {e}")
        # Restore from backup if something went wrong
        if os.path.exists(BACKUP_PATH):
            shutil.copy2(BACKUP_PATH, DB_PATH)
            print("Database restored from backup")
    
    finally:
        if 'new_session' in locals():
            new_session.close()
        if 'old_session' in locals():
            old_session.close()

if __name__ == "__main__":
    migrate_database()