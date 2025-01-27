from plyer import notification
from datetime import date, timedelta
from sqlalchemy import and_
from database import get_session, Reminder, BonsaiTree

def check_and_send_reminders():
    """Check for and send desktop notifications for due reminders"""
    session = get_session()
    today = date.today()
    
    # Find reminders for today
    due_reminders = session.query(Reminder, BonsaiTree).join(BonsaiTree, Reminder.tree_id == BonsaiTree.id)\
        .filter(Reminder.reminder_date <= today).all()
    
    for reminder, tree in due_reminders:
        notification.notify(
            title=f"Bonsai Reminder: Tree {tree.tree_number}",
            message=reminder.reminder_text,
            app_icon=None,  # e.g. 'Path to .ico file'
            timeout=10  # seconds
        )
        
        # Optional: Remove past reminders
        session.delete(reminder)
    
    session.commit()
    session.close()

def create_reminder(tree_id, reminder_date, reminder_text):
    """Create a new reminder for a specific tree"""
    session = get_session()
    try:
        new_reminder = Reminder(
            tree_id=tree_id,
            reminder_date=reminder_date,
            reminder_text=reminder_text
        )
        session.add(new_reminder)
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        print(f"Error creating reminder: {e}")
        return False
    finally:
        session.close()