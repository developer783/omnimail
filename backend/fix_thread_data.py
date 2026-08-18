import os
import sys
import sqlite3

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal
from app.models import Email
import re

def fix_thread_data():
    print("=== RUNNING THREAD DATA BACKFILL & CLEANUP ===")
    
    # 1. SQLAlchemy / App Database
    db = SessionLocal()
    updated_count = 0
    try:
        emails = db.query(Email).all()
        print(f"Inspecting {len(emails)} emails in configured app DB...")
        for e in emails:
            if not e.gmail_thread_id or not e.gmail_thread_id.strip():
                e.gmail_thread_id = e.gmail_message_id
                updated_count += 1
        
        db.commit()
        print(f"Updated {updated_count} emails with missing gmail_thread_id.")
    except Exception as err:
        print(f"Error updating app DB: {err}")
    finally:
        db.close()

    # 2. Direct SQLite backend/email_tool.db
    sqlite_db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "email_tool.db")
    if os.path.exists(sqlite_db_path):
        print(f"Inspecting SQLite database at '{sqlite_db_path}'...")
        conn = sqlite3.connect(sqlite_db_path)
        c = conn.cursor()
        
        # Populate null or empty thread_ids with message_id
        c.execute("""
            UPDATE emails 
            SET gmail_thread_id = gmail_message_id 
            WHERE gmail_thread_id IS NULL OR gmail_thread_id = ''
        """)
        sqlite_updated = c.rowcount
        conn.commit()
        print(f"SQLite backfill updated {sqlite_updated} row(s).")
        
        conn.close()

if __name__ == "__main__":
    fix_thread_data()
