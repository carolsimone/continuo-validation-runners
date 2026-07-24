"""Trino implementation of the WarehouseAdapter port.

Trino's namespace is catalog.schema: the catalog comes from TRINO_CATALOG and every
statement is fully qualified, so the contract's `schema` argument stays an opaque bare
name. Two Trino traits shape this adapter: there is no DROP SCHEMA ... CASCADE, so
teardown drops the schema's tables first; and there are no advisory locks, so
ensure_schema relies on IF NOT EXISTS plus tolerating a concurrent creation.
"""
import logging
import os

from continuo_validation_contract.port import WarehouseAdapter

import trino

from trino.auth import BasicAuthentication

logger = logging.getLogger("continuo_validation_trino")


def _quote(identifier: str) -> str:
    """Double-quote a Trino identifier, escaping any embedded double quotes."""
    escaped = identifier.replace('"', '""')
    return f'"{escaped}"'


class TrinoAdapter(WarehouseAdapter):
    """WarehouseAdapter speaking Trino DDL over the trino DBAPI."""

    def __init__(self, conn: "trino.dbapi.Connection", catalog: str) -> None:
        self._conn = conn
        self._catalog = catalog

    @classmethod
    def required_env(cls) -> list[str]:
        """Vars that must be non-empty before connecting."""
        return ["TRINO_HOST", "TRINO_CATALOG"]

    @classmethod
    def from_env(cls) -> "TrinoAdapter":
        """Connect from TRINO_* env (port 8080, user continuo, http; password optional)."""
        catalog = os.environ["TRINO_CATALOG"]
        user = os.environ.get("TRINO_USER", "continuo")
        http_scheme = os.environ.get("TRINO_HTTP_SCHEME", "http")
        password = os.environ.get("TRINO_PASSWORD", "")
        if password and http_scheme != "https":
            raise ValueError(
                "TRINO_PASSWORD is set but TRINO_HTTP_SCHEME is not 'https'; "
                "Trino refuses basic auth over plaintext"
            )
        conn = trino.dbapi.connect(
            host=os.environ["TRINO_HOST"],
            port=int(os.environ.get("TRINO_PORT", "8080")),
            user=user,
            catalog=catalog,
            http_scheme=http_scheme,
            auth=BasicAuthentication(user, password) if password else None,
        )
        return cls(conn, catalog)

    def _schema_ref(self, schema: str) -> str:
        return f"{_quote(self._catalog)}.{_quote(schema)}"

    def _table_ref(self, schema: str, table: str) -> str:
        return f"{self._schema_ref(schema)}.{_quote(table)}"

    def _execute(self, statement: str) -> list[tuple]:
        """Run one statement to completion and return its rows.

        The trino DBAPI is lazy: execute() only starts the query, so the results must
        be consumed for DDL to actually take effect.
        """
        cur = self._conn.cursor()
        try:
            cur.execute(statement)
            rows: list[tuple] = cur.fetchall()
            return rows
        finally:
            cur.close()

    def _schema_exists(self, schema: str) -> bool:
        rows = self._execute(f"SHOW SCHEMAS FROM {_quote(self._catalog)}")
        return any(row[0] == schema for row in rows)

    def ensure_schema(self, schema: str) -> None:
        """Idempotently create *schema*; safe under concurrent callers."""
        logger.info("ensuring candidate schema %s.%s exists", self._catalog, schema)
        try:
            self._execute(f"CREATE SCHEMA IF NOT EXISTS {self._schema_ref(schema)}")
        except trino.exceptions.TrinoQueryError:
            # IF NOT EXISTS does not close the race: with no advisory locks, a
            # concurrent creator can win between Trino's existence check and the
            # metastore write. The loser surfaces as a user error or — on the
            # Iceberg REST catalog — as an INTERNAL_ERROR query failure, so the
            # error's shape cannot be trusted; only the end state can. Re-raise
            # only if the schema is genuinely absent.
            if not self._schema_exists(schema):
                raise
            logger.info("schema %s already exists (concurrent create); continuing", schema)

    def drop_schema(self, schema: str) -> None:
        """Idempotently drop *schema* and everything in it; no-op if absent.

        DROP SCHEMA ... CASCADE removes the schema's tables and views in one
        statement (the catalog's connector must support CASCADE — Iceberg and
        Hive do).
        """
        logger.info("dropping candidate schema %s.%s", self._catalog, schema)
        self._execute(f"DROP SCHEMA IF EXISTS {self._schema_ref(schema)} CASCADE")

    def build_empty_from_sql(self, schema: str, table: str, compiled_sql: str) -> None:
        """Create ``schema.table`` empty, shaped by the compiled SELECT."""
        # Strip any trailing terminator so the SELECT nests cleanly inside AS ( ... ).
        inner = compiled_sql.strip().rstrip(";").strip()
        ref = self._table_ref(schema, table)
        self._execute(f"DROP TABLE IF EXISTS {ref}")
        self._execute(f"CREATE TABLE {ref} AS ({inner}) WITH NO DATA")

    def clone_empty_from_prod(self, candidate_schema: str, prod_schema: str, table: str) -> None:
        """Create ``candidate_schema.table`` empty, shaped like ``prod_schema.table``."""
        ref = self._table_ref(candidate_schema, table)
        self._execute(f"DROP TABLE IF EXISTS {ref}")
        self._execute(
            f"CREATE TABLE {ref} AS "
            f"SELECT * FROM {self._table_ref(prod_schema, table)} WITH NO DATA"
        )

    def close(self) -> None:
        """Release the underlying connection."""
        self._conn.close()
