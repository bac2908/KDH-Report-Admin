"""Small DB-API bridge; the application uses the same SQL on SQLite and Postgres."""
import sqlite3
from contextlib import contextmanager


class Connection:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def sql(query):
        # Application queries are constants; values are always bound separately.
        return query.replace('%', '%%').replace('?', '%s')

    def execute(self, query, args=()):
        return self.db.execute(self.sql(query), args)

    def executemany(self, query, args):
        return self.db.cursor().executemany(self.sql(query), args)

    def executescript(self, script):
        script = script.replace('PRAGMA journal_mode=WAL;', '').replace(' BLOB ', ' BYTEA ')
        for statement in script.split(';'):
            if statement.strip():
                self.db.execute(statement)


@contextmanager
def connect(url, immediate=False):
    import psycopg
    from psycopg.rows import dict_row

    # No process-wide pool: Neon provides a pooled URL, and functions can disappear.
    with psycopg.connect(url, connect_timeout=10, prepare_threshold=None, row_factory=dict_row) as db:
        try:
            db.execute("SET LOCAL statement_timeout = '25s'")
            db.execute("SET LOCAL lock_timeout = '10s'")
            if immediate:
                # Match BEGIN IMMEDIATE for short read/modify/write transactions.
                # Transaction-scoped locks also work with Neon's transaction pooler.
                db.execute('SELECT pg_advisory_xact_lock(684204901)')
            yield Connection(db)
        except psycopg.IntegrityError as exc:
            raise sqlite3.IntegrityError('Database constraint violation') from exc
