import os
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from database.models import Base

DEFAULT_DATABASE_URL = "sqlite:///./data/bot.db"


def _resolve_database_url() -> str:
    url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    if url.startswith("sqlite:///./"):
        db_path = url.replace("sqlite:///./", "", 1)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return url


DATABASE_URL = _resolve_database_url()

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

_USER_HOME_COLUMNS = (
    ("home_latitude", "REAL"),
    ("home_longitude", "REAL"),
    ("home_location_name", "VARCHAR(255)"),
    ("report_enabled", "BOOLEAN"),
    ("report_time", "VARCHAR(5)"),
    ("include_events", "BOOLEAN"),
    ("include_birthdays", "BOOLEAN"),
    ("include_weather", "BOOLEAN"),
    ("last_report_date", "DATE"),
    ("locale", "VARCHAR(5)"),
)


def _migrate_sqlite_columns() -> None:
    if not DATABASE_URL.startswith("sqlite"):
        return
    with engine.connect() as conn:
        existing = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA table_info(users)").fetchall()
        }
        for column_name, column_type in _USER_HOME_COLUMNS:
            if column_name not in existing:
                conn.exec_driver_sql(
                    f"ALTER TABLE users ADD COLUMN {column_name} {column_type}"
                )
        conn.commit()


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _migrate_sqlite_columns()


@contextmanager
def get_session():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
