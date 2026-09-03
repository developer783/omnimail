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

    # 2. Backfill reclassification of existing outbound emails
    try:
        # Get all distinct thread_ids that have AT LEAST ONE inbound message
        inbound_threads = set(
            r[0] for r in db.query(Email.gmail_thread_id)
            .filter(
                Email.sender.notilike("Me %"),
                Email.gmail_thread_id.isnot(None),
                Email.gmail_thread_id != ""
            ).distinct().all()
        )

        outbound_emails = db.query(Email).filter(
            (Email.sender.ilike("Me %")) | (Email.folder_status.in_(["sent", "replied"]))
        ).all()

        moved_to_sent = 0
        stayed_replied = 0

        for email in outbound_emails:
            has_inbound = email.gmail_thread_id in inbound_threads
            if has_inbound:
                if not email.is_reply or email.folder_status != "replied":
                    email.is_reply = True
                    email.folder_status = "replied"
                stayed_replied += 1
            else:
                if email.is_reply or email.folder_status != "sent":
                    email.is_reply = False
                    email.folder_status = "sent"
                moved_to_sent += 1

        db.commit()
        logger.info(
            f"[Reclassification Complete] Analyzed {len(outbound_emails)} outbound email(s): "
            f"{stayed_replied} remain in 'Replied' (true reply-to-inbound), "
            f"{moved_to_sent} moved to 'Sent' (standalone cold outreach)."
        )
        return {
            "total_outbound": len(outbound_emails),
            "replied_count": stayed_replied,
            "sent_count": moved_to_sent
        }
    except Exception as e:
        logger.error(f"Error executing backfill reclassification migration: {e}")
        db.rollback()
        return {"error": str(e)}
