import logging
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.models import Email

logger = logging.getLogger("migrations")

def run_migrations_and_backfill(db: Session):
    """
    1. Ensures 'is_reply' column exists on 'emails' table (for Postgres & SQLite).
    2. Runs a one-time backfill reclassification query:
       - Outbound emails in threads WITH prior inbound messages -> is_reply = True, folder_status = 'replied'
       - Outbound emails in threads WITHOUT inbound messages -> is_reply = False, folder_status = 'sent'
    """
    # 1. Add is_reply column if missing
    try:
        bind = db.get_bind()
        dialect_name = bind.dialect.name
        
        column_exists = False
        if dialect_name == "postgresql":
            res = db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='emails' AND column_name='is_reply'")).fetchone()
            column_exists = bool(res)
        else:
            res = db.execute(text("PRAGMA table_info(emails)")).fetchall()
            column_exists = any(row[1] == "is_reply" for row in res)

        if not column_exists:
            logger.info("Adding 'is_reply' column to 'emails' table...")
            db.execute(text("ALTER TABLE emails ADD COLUMN is_reply BOOLEAN DEFAULT FALSE NOT NULL"))
            db.commit()
            logger.info("Successfully added 'is_reply' column to 'emails' table.")
    except Exception as e:
        logger.warning(f"Error checking/adding 'is_reply' column: {e}")
        db.rollback()

    # 2. Add snippet column if missing, then fill it in small batches (bounded memory)
    try:
        bind = db.get_bind()
        if bind.dialect.name == "postgresql":
            res = db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='emails' AND column_name='snippet'")).fetchone()
            snippet_exists = bool(res)
        else:
            res = db.execute(text("PRAGMA table_info(emails)")).fetchall()
            snippet_exists = any(row[1] == "snippet" for row in res)

        if not snippet_exists:
            logger.info("Adding 'snippet' column to 'emails' table...")
            db.execute(text("ALTER TABLE emails ADD COLUMN snippet VARCHAR(300)"))
            db.commit()

        from app.gmail_service import make_snippet
        filled = 0
        while True:
            rows = db.query(Email.id, Email.html_body).filter(Email.snippet.is_(None)).limit(25).all()
            if not rows:
                break
            for email_id, body in rows:
                db.query(Email).filter(Email.id == email_id).update(
                    {Email.snippet: make_snippet(body or "")[:300]}, synchronize_session=False
                )
            db.commit()
            filled += len(rows)
            del rows
        if filled:
            logger.info(f"Backfilled snippets for {filled} email(s).")
    except Exception as e:
        logger.warning(f"Error adding/backfilling 'snippet' column: {e}")
        db.rollback()

    # 3. Backfill reclassification of existing outbound emails, as bulk UPDATEs so that no
    # email rows (and their potentially large bodies) are loaded into memory at startup.
    try:
        inbound_tids = db.query(Email.gmail_thread_id).filter(
            Email.sender.notilike("Me %"),
            Email.gmail_thread_id.isnot(None),
            Email.gmail_thread_id != ""
        ).distinct()
        is_outbound = (Email.sender.ilike("Me %")) | (Email.folder_status.in_(["sent", "replied"]))

        replied_count = db.query(Email).filter(
            is_outbound,
            Email.gmail_thread_id.in_(inbound_tids),
            (Email.is_reply == False) | (Email.folder_status != "replied")
        ).update({Email.is_reply: True, Email.folder_status: "replied"}, synchronize_session=False)

        sent_count = db.query(Email).filter(
            is_outbound,
            (Email.gmail_thread_id.is_(None)) | ~Email.gmail_thread_id.in_(inbound_tids),
            (Email.is_reply == True) | (Email.folder_status != "sent")
        ).update({Email.is_reply: False, Email.folder_status: "sent"}, synchronize_session=False)

        db.commit()
        logger.info(
            f"[Reclassification Complete] {replied_count} outbound email(s) set to 'Replied', "
            f"{sent_count} set to 'Sent'."
        )
        return {"replied_updated": replied_count, "sent_updated": sent_count}
    except Exception as e:
        logger.error(f"Error executing backfill reclassification migration: {e}")
        db.rollback()
        return {"error": str(e)}
