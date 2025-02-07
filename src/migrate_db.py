# src/migrate_db.py
import os
import sys
from sqlalchemy import create_engine, text

# Get the absolute path to the data directory
DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data'))
DB_PATH = os.path.join(DATA_DIR, 'bonsai.db')

def run_migration():
    """
    Run migration to add is_archived column to trees table
    """
    # Create engine using the same database path as in database.py
    engine = create_engine(f'sqlite:///{DB_PATH}')
    
    # SQL commands to run
    commands = [
        # Add is_archived column with default value of 0
        """
        ALTER TABLE trees
        ADD COLUMN is_archived INTEGER DEFAULT 0;
        """,
        
        # Update any existing NULL values to 0
        """
        UPDATE trees
        SET is_archived = 0
        WHERE is_archived IS NULL;
        """,
        
        # Add NOT NULL constraint
        """
        PRAGMA foreign_keys=off;
        BEGIN TRANSACTION;

        CREATE TABLE trees_new (
            id INTEGER PRIMARY KEY,
            tree_number VARCHAR(50) NOT NULL UNIQUE,
            tree_name VARCHAR(50) NOT NULL UNIQUE,
            species_id INTEGER NOT NULL,
            date_acquired DATETIME NOT NULL,
            origin_date DATETIME NOT NULL,
            current_girth FLOAT,
            notes TEXT,
            is_archived INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(species_id) REFERENCES species(id)
        );

        INSERT INTO trees_new 
        SELECT id, tree_number, tree_name, species_id, date_acquired, 
               origin_date, current_girth, notes, COALESCE(is_archived, 0)
        FROM trees;

        DROP TABLE trees;
        ALTER TABLE trees_new RENAME TO trees;

        COMMIT;
        PRAGMA foreign_keys=on;
        """
    ]
    
    try:
        with engine.connect() as connection:
            # SQLite doesn't support ALTER COLUMN, so we'll execute commands one by one
            for command in commands:
                # Split the command into individual statements
                statements = command.strip().split(';')
                for statement in statements:
                    if statement.strip():
                        connection.execute(text(statement))
                connection.commit()
        print("Migration completed successfully!")
        
    except Exception as e:
        print(f"Error during migration: {str(e)}")
        print("Rolling back changes...")
        
        # Rollback command to remove column if something goes wrong
        rollback = """
        PRAGMA foreign_keys=off;
        BEGIN TRANSACTION;

        CREATE TABLE trees_backup AS SELECT 
            id, tree_number, tree_name, species_id, date_acquired, 
            origin_date, current_girth, notes
        FROM trees;

        DROP TABLE trees;
        ALTER TABLE trees_backup RENAME TO trees;

        COMMIT;
        PRAGMA foreign_keys=on;
        """
        
        try:
            with engine.connect() as connection:
                statements = rollback.strip().split(';')
                for statement in statements:
                    if statement.strip():
                        connection.execute(text(statement))
                connection.commit()
            print("Rollback completed successfully")
        except Exception as e:
            print(f"Error during rollback: {str(e)}")
            print("Manual intervention may be required")

if __name__ == "__main__":
    # Confirm before running
    response = input("This will modify your database schema. Are you sure you want to continue? (y/n): ")
    if response.lower() == 'y':
        run_migration()
    else:
        print("Migration cancelled")