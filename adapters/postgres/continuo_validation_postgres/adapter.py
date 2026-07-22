"""Postgres implementation of the WarehouseAdapter port.

DDL matches the prior continuo-internal validation-runner exactly: empty builds via
``CREATE TABLE … AS (…) WITH NO DATA``; empty clones via ``CTAS … WHERE 1=0``;
schema creation serialized on a session advisory lock because parallel root
validation nodes race on ``CREATE SCHEMA``.
"""
import os

import psycopg2

from psycopg2 import errors as pg_errors
from psycopg2 import sql as pg_sql

from continuo_validation_core.port import WarehouseAdapter


class PostgresAdapter(WarehouseAdapter):
    """WarehouseAdapter speaking postgres DDL over a psycopg2 connection."""

    def __init__(self, conn: "psycopg2.extensions.connection") -> None:
        self._conn = conn
        self._conn.autocommit = True

    @classmethod
    def required_env(cls) -> list[str]:
        """Vars that must be non-empty before connecting."""
        return ["DBT_POSTGRES_HOST", "DBT_POSTGRES_DB", "DBT_POSTGRES_USER"]

    @classmethod
    def from_env(cls) -> "PostgresAdapter":
        """Connect from DBT_POSTGRES_* env (port defaults 5432, password empty)."""
        conn = psycopg2.connect(
            host=os.environ["DBT_POSTGRES_HOST"],
            port=os.environ.get("DBT_POSTGRES_PORT", "5432"),
            dbname=os.environ["DBT_POSTGRES_DB"],
            user=os.environ["DBT_POSTGRES_USER"],
            password=os.environ.get("DBT_POSTGRES_PASSWORD", ""),
        )
        return cls(conn)

    def ensure_schema(self, schema: str) -> None:
        """Idempotently create *schema*; safe under concurrent callers."""
        # Race-safe: root validation nodes dispatch in parallel and can collide on
        # CREATE SCHEMA. Serialize on a session advisory lock keyed by schema name;
        # tolerate DuplicateSchema/UniqueViolation as a second line of defense.
        with self._conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(hashtext(%s))", (schema,))
            try:
                stmt = pg_sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(
                    pg_sql.Identifier(schema)
                )
                print(f"-- ensuring candidate schema {schema} exists", flush=True)
                try:
                    cur.execute(stmt)
                except (pg_errors.DuplicateSchema, pg_errors.UniqueViolation):
                    print(
                        f"-- schema {schema} already exists (concurrent create); continuing",
                        flush=True,
                    )
            finally:
                cur.execute("SELECT pg_advisory_unlock(hashtext(%s))", (schema,))

    def build_empty_from_sql(self, schema: str, table: str, compiled_sql: str) -> None:
        """Create ``schema.table`` empty, shaped by the compiled SELECT."""
        # Strip any trailing terminator so the SELECT nests cleanly inside AS ( ... ).
        inner = compiled_sql.strip().rstrip(";").strip()
        with self._conn.cursor() as cur:
            cur.execute(
                pg_sql.SQL("DROP TABLE IF EXISTS {}.{}").format(
                    pg_sql.Identifier(schema), pg_sql.Identifier(table)
                )
            )
            cur.execute(
                pg_sql.SQL("CREATE TABLE {}.{} AS ({}) WITH NO DATA").format(
                    pg_sql.Identifier(schema),
                    pg_sql.Identifier(table),
                    pg_sql.SQL(inner),
                )
            )

    def clone_empty_from_prod(self, candidate_schema: str, prod_schema: str, table: str) -> None:
        """Create ``candidate_schema.table`` empty, shaped like ``prod_schema.table``."""
        with self._conn.cursor() as cur:
            cur.execute(
                pg_sql.SQL("DROP TABLE IF EXISTS {}.{}").format(
                    pg_sql.Identifier(candidate_schema), pg_sql.Identifier(table)
                )
            )
            cur.execute(
                pg_sql.SQL(
                    "CREATE TABLE {}.{} AS SELECT * FROM {}.{} WHERE 1=0"
                ).format(
                    pg_sql.Identifier(candidate_schema),
                    pg_sql.Identifier(table),
                    pg_sql.Identifier(prod_schema),
                    pg_sql.Identifier(table),
                )
            )

    def close(self) -> None:
        """Release the underlying connection."""
        self._conn.close()
