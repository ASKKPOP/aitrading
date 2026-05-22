import os
import sys

from alembic import context

# Make service/server importable so we can load config.
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config import settings  # noqa: E402


def _db_url() -> str:
    url = settings.database_url
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Alembic migrations require a MySQL connection."
        )
    return url


def run_migrations_offline() -> None:
    """Generate SQL without connecting — useful for reviewing DDL."""
    context.configure(
        url=_db_url(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations using a live MySQL connection via SQLAlchemy + PyMySQL."""
    from sqlalchemy import create_engine  # noqa: PLC0415

    connectable = create_engine(_db_url())
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
