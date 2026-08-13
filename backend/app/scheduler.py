import datetime
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.database import SessionLocal
from app.models import ConnectedAccount, Email
from app.gmail_service import fetch_and_store_emails_for_account

logger = logging.getLogger("scheduler")

scheduler = AsyncIOScheduler()

def purge_expired_inbound_emails():
    """
    Background rolling purge job:
    Deletes inbound emails received more than 24 hours ago (received_at < NOW() - 24 hours).
    Sent replies / outbound emails (folder_status == 'replied' or sender starting with 'Me ') are EXCLUDED
    from deletion so thread history is preserved.
    """
    db = SessionLocal()
    try:
        cutoff_24h = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
        
        # Scope deletion to inbound emails older than 24h
        deleted_count = db.query(Email).filter(
            Email.received_at < cutoff_24h,
            Email.folder_status != "replied",
            ~Email.sender.ilike("Me %")
        ).delete(synchronize_session=False)

        db.commit()
        if deleted_count > 0:
            logger.info(f"[Purge Job] Auto-deleted {deleted_count} inbound email(s) older than 24 hours.")
    except Exception as e:
        logger.error(f"[Purge Job Error] Failed executing 24h rolling email purge: {e}")
    finally:
        db.close()

def sync_all_connected_accounts():
    """Background task function run periodically by APScheduler."""
    logger.info("Starting background email sync & 24h rolling purge job...")
    
    # 1. Run 24h rolling purge first
    purge_expired_inbound_emails()

    # 2. Fetch new emails within 24h window
    db = SessionLocal()
    try:
        accounts = db.query(ConnectedAccount).all()
        logger.info(f"Syncing {len(accounts)} connected Google account(s)...")
        total_fetched = 0
        for acc in accounts:
            try:
                count = fetch_and_store_emails_for_account(db, acc)
                total_fetched += count
            except Exception as e:
                logger.error(f"Error background syncing account {acc.google_email}: {e}")
        logger.info(f"Background sync complete. {total_fetched} new email(s) stored.")
    finally:
        db.close()

def start_scheduler():
    """Initializes and starts the periodic scheduler (runs every 5 minutes)."""
    scheduler.add_job(
        sync_all_connected_accounts,
        trigger="interval",
        minutes=5,
        id="gmail_sync_job",
        replace_existing=True
    )
    scheduler.start()
    logger.info("APScheduler started successfully (5-minute interval for sync & 24h rolling purge).")

def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("APScheduler shut down.")
