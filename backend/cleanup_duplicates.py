import os
import sys
import sqlite3

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def cleanup_sqlite():
    sqlite_db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "email_tool.db")
    if not os.path.exists(sqlite_db_path):
        print("SQLite database not found at", sqlite_db_path)
        return

    print("=== CLEANING UP SQLITE DATABASE DUPLICATES ===")
    conn = sqlite3.connect(sqlite_db_path)
    c = conn.cursor()

    # Backfill missing gmail_thread_id
    c.execute("""
        UPDATE emails 
        SET gmail_thread_id = gmail_message_id 
        WHERE gmail_thread_id IS NULL OR gmail_thread_id = ''
    """)
    print(f"SQLite thread backfill updated {c.rowcount} row(s).")

    # Find duplicates by (account_id, gmail_message_id)
    c.execute("""
        DELETE FROM emails
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM emails
            GROUP BY account_id, gmail_message_id
        )
    """)
    deleted_count = c.rowcount
    conn.commit()
    conn.close()
    print(f"SQLite cleanup deleted {deleted_count} duplicate row(s).")

def cleanup_postgres():
    print("\n=== CLEANING UP POSTGRES DATABASE DUPLICATES ===")
    try:
        from app.database import SessionLocal, engine
        from app.models import Email
        from sqlalchemy import text

        db = SessionLocal()
        # Delete duplicate rows keeping MIN(id)
        with engine.connect() as conn:
            res = conn.execute(text("""
                DELETE FROM emails
                WHERE id NOT IN (
                    SELECT MIN(id)
                    FROM emails
                    GROUP BY account_id, gmail_message_id
                )
            """))
            conn.commit()
            print(f"Postgres cleanup deleted {res.rowcount} duplicate row(s).")
        db.close()
    except Exception as err:
        print(f"Postgres cleanup skipped or error: {err}")

if __name__ == "__main__":
    cleanup_sqlite()
    cleanup_postgres()
