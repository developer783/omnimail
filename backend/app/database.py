from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings

db_url = settings.DATABASE_URL
connect_args = {}
if db_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False

# Keep the connection pool small: each idle Postgres connection costs memory on both the app
# and the database side, and a single-worker app on a small instance never needs many at once.
pool_kwargs = {} if db_url.startswith("sqlite") else {"pool_size": 3, "max_overflow": 2, "pool_recycle": 300}

engine = create_engine(
    db_url,
    connect_args=connect_args,
    pool_pre_ping=True,
    **pool_kwargs
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
