"""Database connection and transaction handling using APSW."""

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import apsw
import click
from flask import current_app, g


def get_db() -> apsw.Connection:
    """Get the database connection for the current request."""
    if "db" not in g:
        db_path = current_app.config["DATABASE_PATH"]
        # Ensure parent directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        g.db = apsw.Connection(db_path)
        # Set busy timeout first so other PRAGMAs can wait for locks
        g.db.execute("PRAGMA busy_timeout = 5000;")
        # Enable foreign keys
        g.db.execute("PRAGMA foreign_keys = ON;")
        # Use WAL mode for better concurrency
        g.db.execute("PRAGMA journal_mode = WAL;")
    return g.db


def close_db(e: BaseException | None = None) -> None:
    """Close the database connection at the end of the request."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


@contextmanager
def transaction() -> Generator[apsw.Cursor]:
    """
    Context manager for database transactions.
    Automatically commits on success, rolls back on exception.

    Usage:
        with transaction() as cursor:
            cursor.execute("INSERT INTO ...")
            cursor.execute("UPDATE ...")
        # Auto-commits here
    """
    db = get_db()
    cursor = db.cursor()
    cursor.execute("BEGIN IMMEDIATE;")
    try:
        yield cursor
        cursor.execute("COMMIT;")
    except Exception:
        cursor.execute("ROLLBACK;")
        raise


def init_db() -> None:
    """Initialize the database with the schema."""
    db = get_db()
    schema_path = Path(__file__).parent.parent.parent / "database" / "schema.sql"

    with open(schema_path) as f:
        # APSW requires iterating over execute() result to run all statements
        for _ in db.execute(f.read()):
            pass


def get_schema_version() -> int:
    """Get the current schema version from db_metadata."""
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("SELECT value FROM db_metadata WHERE key = 'schema_version'")
        row = cursor.fetchone()
        return int(row[0]) if row else 0
    except apsw.SQLError:
        return 0


def migrate_db() -> None:
    """Run pending database migrations."""
    current_version = get_schema_version()
    migrations_dir = Path(__file__).parent.parent.parent / "database" / "migrations"

    if not migrations_dir.exists():
        return

    # Find migration files: NNN_description.sql where NNN > current_version
    migration_files: list[tuple[int, Path]] = []
    for sql_file in sorted(migrations_dir.glob("*.sql")):
        prefix = sql_file.stem.split("_", 1)[0]
        try:
            version = int(prefix)
        except ValueError:
            continue
        if version > current_version:
            migration_files.append((version, sql_file))

    migration_files.sort()

    db = get_db()
    for version, sql_file in migration_files:
        click.echo(f"Applying migration {sql_file.name} (version {version})...")
        with open(sql_file) as f:
            for _ in db.execute(f.read()):
                pass
        click.echo(f"  Applied {sql_file.name}")

    if not migration_files:
        click.echo(f"Database already at version {current_version}, no migrations to apply.")


@click.command("init-db")
def init_db_command() -> None:
    """Clear existing data and create new tables."""
    init_db()
    click.echo("Database initialized.")


@click.command("migrate-db")
def migrate_db_command() -> None:
    """Run pending database migrations."""
    migrate_db()
    click.echo("Migrations complete.")
