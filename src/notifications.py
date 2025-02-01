import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import schedule
import time
import threading
from sqlalchemy import and_
from typing import Optional

class ReminderNotifier:
    def __init__(self, email: str, smtp_server: str, smtp_port: int, 
                 smtp_username: str, smtp_password: str):
        """Initialize the reminder notification system.
        
        Args:
            email: Email address to send notifications to
            smtp_server: SMTP server address (e.g., 'smtp.gmail.com')
            smtp_port: SMTP port (e.g., 587 for TLS)
            smtp_username: SMTP login username
            smtp_password: SMTP login password
        """
        self.email = email
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.smtp_username = smtp_username
        self.smtp_password = smtp_password
        self.running = False
        self.scheduler_thread: Optional[threading.Thread] = None

    def send_notification(self, tree_name: str, tree_number: str, message: str) -> None:
        """Send an email notification for a tree reminder."""
        msg = MIMEMultipart()
        msg['From'] = self.smtp_username
        msg['To'] = self.email
        msg['Subject'] = f"Tree Reminder: {tree_name} ({tree_number})"
        
        body = f"""Tree Reminder:
Tree: {tree_name} ({tree_number})
Message: {message}

This is an automated reminder from your Tree Management System."""
        
        msg.attach(MIMEText(body, 'plain'))
        
        try:
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)
        except Exception as e:
            print(f"Failed to send notification: {e}")

    def check_reminders(self, db) -> None:
        """Check for due reminders and send notifications."""
        try:
            # Query for reminders that are due today and haven't been sent
            today = datetime.now().date()
            due_reminders = db.query(Reminder, Tree).join(Tree).filter(
                and_(
                    Reminder.reminder_date <= today,
                    Reminder.notification_sent == False
                )
            ).all()
            
            for reminder, tree in due_reminders:
                self.send_notification(
                    tree_name=tree.tree_name,
                    tree_number=tree.tree_number,
                    message=reminder.message
                )
                
                # Mark reminder as sent
                reminder.notification_sent = True
                db.commit()
        except Exception as e:
            print(f"Error checking reminders: {e}")
        finally:
            db.close()

    def run_scheduler(self) -> None:
        """Run the scheduler to check for reminders daily."""
        while self.running:
            schedule.run_pending()
            time.sleep(60)

    def start(self, db_session) -> None:
        """Start the reminder notification system."""
        if not self.running:
            self.running = True
            
            # Schedule daily reminder check
            schedule.every().day.at("09:00").do(self.check_reminders, db_session)
            
            # Start scheduler in separate thread
            self.scheduler_thread = threading.Thread(target=self.run_scheduler)
            self.scheduler_thread.start()

    def stop(self) -> None:
        """Stop the reminder notification system."""
        self.running = False
        if self.scheduler_thread:
            self.scheduler_thread.join()