import os
import sys
import sqlite3

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def diagnose_postgres():
    print("=================== POSTGRES (omnimail) DIAGNOSTICS ===================")
    try:
        from app.database import SessionLocal
        from app.models import Email
        from sqlalchemy import func

        db = SessionLocal()

        print("\n--- ITEM 2: Postgres Thread Messages ---")
        threads = db.query(Email.gmail_thread_id).distinct().all()
        for t in threads:
            tid = t[0]
            msgs = db.query(Email.id, Email.gmail_message_id, Email.gmail_thread_id, Email.subject, Email.sender).filter(Email.gmail_thread_id == tid).all()
            print(f"Thread ID: {tid} ({len(msgs)} rows):")
            for m in msgs:
                print("  ", dict(id=m.id, gmail_message_id=m.gmail_message_id, gmail_thread_id=m.gmail_thread_id, subject=m.subject, sender=m.sender))

        print("\n--- ITEM 3: Postgres Available Candidate Thread ---")
        cand_msgs = db.query(Email.id, Email.subject, Email.gmail_thread_id, Email.sender, Email.folder_status).filter(
            (Email.subject.ilike("%Candidate%")) | (Email.subject.ilike("%AI Engineer%"))
        ).all()
        print(f"Available Candidate rows count: {len(cand_msgs)}")
        for m in cand_msgs:
            print("  ", dict(id=m.id, subject=m.subject, thread_id=m.gmail_thread_id, sender=m.sender, folder_status=m.folder_status))

        print("\n--- ITEM 4: Postgres Duplicate gmail_message_id Check ---")
        dups = db.query(Email.gmail_message_id, func.count(Email.id)).group_by(Email.gmail_message_id).having(func.count(Email.id) > 1).all()
        print(f"Postgres duplicate gmail_message_id count: {len(dups)}")
        for d in dups:
            print("  ", d)

        print("\n--- ITEM 5: Postgres jmpatil / Sent Reply Query ---")
        sent_msgs = db.query(Email.id, Email.subject, Email.recipient, Email.sender, Email.folder_status).filter(
            (Email.sender.ilike("%jmpatil%")) | (Email.recipient.ilike("%jmpatil%")) | (Email.folder_status == "replied") | (Email.sender.ilike("Me %"))
        ).all()
        print(f"Outbound / Replied / jmpatil rows count: {len(sent_msgs)}")
        for m in sent_msgs:
            print("  ", dict(id=m.id, subject=m.subject, recipient=m.recipient, sender=m.sender, folder_status=m.folder_status))

        db.close()
    except Exception as e:
        print("Postgres error:", e)

def diagnose_sqlite():
    print("\n=================== SQLITE (email_tool.db) DIAGNOSTICS ===================")
    sqlite_db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "email_tool.db")
    if not os.path.exists(sqlite_db_path):
        print(f"SQLite DB not found at {sqlite_db_path}")
        return
    try:
        conn = sqlite3.connect(sqlite_db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        print("\n--- ITEM 2: SQLite Thread Messages ---")
        c.execute("SELECT DISTINCT gmail_thread_id FROM emails")
        threads = c.fetchall()
        for t in threads:
            tid = t[0]
            c.execute("SELECT id, gmail_message_id, gmail_thread_id, subject, sender FROM emails WHERE gmail_thread_id = ?", (tid,))
            msgs = c.fetchall()
            print(f"Thread ID: {tid} ({len(msgs)} rows):")
            for m in msgs:
                print("  ", dict(m))

        print("\n--- ITEM 3: SQLite Available Candidate Thread ---")
        c.execute("SELECT id, subject, gmail_thread_id, sender, folder_status FROM emails WHERE subject LIKE '%Candidate%' OR subject LIKE '%AI Engineer%'")
        cand_msgs = c.fetchall()
        print(f"Available Candidate rows count: {len(cand_msgs)}")
        for m in cand_msgs:
            print("  ", dict(m))

        print("\n--- ITEM 4: SQLite Duplicate gmail_message_id Check ---")
        c.execute("SELECT gmail_message_id, COUNT(*) FROM emails GROUP BY gmail_message_id HAVING COUNT(*) > 1")
        sql_dups = c.fetchall()
        print(f"SQLite duplicate gmail_message_id count: {len(sql_dups)}")
        for d in sql_dups:
            print("  ", dict(d))

        print("\n--- ITEM 5: SQLite jmpatil / Sent Reply Query ---")
        c.execute("SELECT id, subject, recipient, sender, folder_status FROM emails WHERE sender LIKE '%jmpatil%' OR recipient LIKE '%jmpatil%' OR folder_status = 'replied' OR sender LIKE 'Me %'")
        sql_sent = c.fetchall()
        print(f"SQLite outbound / replied rows count: {len(sql_sent)}")
        for m in sql_sent:
            print("  ", dict(m))

        conn.close()
    except Exception as e:
        print("SQLite error:", e)

if __name__ == "__main__":
    diagnose_postgres()
    diagnose_sqlite()
