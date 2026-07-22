"""Unit tests for the postgres adapter — mocked cursor, no live database."""
from importlib.metadata import entry_points
from unittest.mock import MagicMock, patch

import pytest
import sqlglot

from psycopg2 import errors as pg_errors
from psycopg2 import sql as pg_sql

from continuo_validation_core.port import WarehouseAdapter
from continuo_validation_postgres import adapter as adapter_mod
from continuo_validation_postgres.adapter import PostgresAdapter


class _FakeCursor:
    """Records execute() calls; optionally raises a given error on the CREATE.

    The CREATE statements are psycopg2 Composed objects; the advisory lock/unlock
    are plain strings — used to tell them apart (mirrors test_validation_runner).
    """

    def __init__(self, raise_on_composed=None):
        self._raise = raise_on_composed
        self.calls = []  # (statement, params)

    def execute(self, statement, params=None):
        self.calls.append((statement, params))
        if self._raise is not None and not isinstance(statement, str):
            raise self._raise

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeConn:
    def __init__(self, cur):
        self._cur = cur
        self.autocommit = False
        self.closed = False

    def cursor(self):
        return self._cur

    def close(self):
        self.closed = True


def _stmt_text(composed) -> str:
    """Concatenate the literal SQL fragments of a Composed (DB-free rendering)."""
    return "".join(p.string for p in composed.seq if isinstance(p, pg_sql.SQL))


def _rendered(cur):
    return [s if isinstance(s, str) else s.__class__.__name__ for s, _ in cur.calls]


def test_postgres_adapter_sets_autocommit():
    """Test that constructing the adapter sets autocommit on the connection."""
    conn = _FakeConn(_FakeCursor())
    PostgresAdapter(conn)
    assert conn.autocommit is True


def test_ensure_schema_locks_creates_unlocks():
    """Test that ensure_schema takes the advisory lock, creates, then unlocks."""
    cur = _FakeCursor()
    PostgresAdapter(_FakeConn(cur)).ensure_schema("_candidate_relA")
    rendered = _rendered(cur)
    assert "pg_advisory_lock" in rendered[0]
    assert rendered[1] == "Composed"  # CREATE SCHEMA
    assert "pg_advisory_unlock" in rendered[2]
    assert len(cur.calls) == 3


def test_ensure_schema_tolerates_duplicate_schema_and_unlocks():
    """Test that ensure_schema swallows a concurrent DuplicateSchema and unlocks."""
    cur = _FakeCursor(raise_on_composed=pg_errors.DuplicateSchema("exists"))
    PostgresAdapter(_FakeConn(cur)).ensure_schema("_candidate_relB")  # must not raise
    assert "pg_advisory_unlock" in _rendered(cur)[-1]


def test_ensure_schema_propagates_unexpected_error_but_unlocks():
    """Test that ensure_schema re-raises unexpected errors but still unlocks."""
    cur = _FakeCursor(raise_on_composed=RuntimeError("connection reset"))
    with pytest.raises(RuntimeError, match="connection reset"):
        PostgresAdapter(_FakeConn(cur)).ensure_schema("_candidate_relC")
    assert "pg_advisory_unlock" in _rendered(cur)[-1]


def test_build_empty_from_sql_drops_then_ctas_with_no_data():
    """Test that build_empty_from_sql drops then creates the table WITH NO DATA."""
    cur = _FakeCursor()
    PostgresAdapter(_FakeConn(cur)).build_empty_from_sql(
        "_candidate_relA", "orders", "SELECT 1 AS id"
    )
    assert _rendered(cur) == ["Composed", "Composed"]
    drop, create = cur.calls[0][0], cur.calls[1][0]
    assert "DROP TABLE IF EXISTS" in _stmt_text(drop)
    create_text = _stmt_text(create)
    assert "CREATE TABLE" in create_text
    assert "WITH NO DATA" in create_text


def test_build_empty_from_sql_strips_trailing_semicolon():
    """Test that a trailing semicolon on the compiled SQL is stripped before CTAS."""
    cur = _FakeCursor()
    PostgresAdapter(_FakeConn(cur)).build_empty_from_sql(
        "_candidate_relA", "orders", "SELECT 1 AS id ;  "
    )
    # The inner SQL is embedded as a pg_sql.SQL part of the CREATE Composed; the
    # trailing ';' must be stripped so it nests inside AS ( ... ).
    inner = [p.string for p in cur.calls[1][0].seq if isinstance(p, pg_sql.SQL)]
    assert any(s.strip() == "SELECT 1 AS id" for s in inner)


def test_clone_empty_from_prod_drops_then_ctas_where_false():
    """Test that clone_empty_from_prod drops then creates the table WHERE 1=0."""
    cur = _FakeCursor()
    PostgresAdapter(_FakeConn(cur)).clone_empty_from_prod(
        "_candidate_relA", "analytics", "seed_fx_transactions"
    )
    assert _rendered(cur) == ["Composed", "Composed"]
    create_text = _stmt_text(cur.calls[1][0])
    assert "CREATE TABLE" in create_text
    assert "SELECT * FROM" in create_text
    assert "WHERE 1=0" in create_text


def test_required_env_names_connection_vars():
    """Test that required_env lists the three mandatory DBT_POSTGRES_* vars."""
    assert PostgresAdapter.required_env() == [
        "DBT_POSTGRES_HOST", "DBT_POSTGRES_DB", "DBT_POSTGRES_USER",
    ]


def test_from_env_connects_with_env_values(monkeypatch):
    """Test that from_env connects using env values and defaults the port."""
    for k, v in {
        "DBT_POSTGRES_HOST": "h", "DBT_POSTGRES_DB": "d",
        "DBT_POSTGRES_USER": "u", "DBT_POSTGRES_PASSWORD": "p",
    }.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("DBT_POSTGRES_PORT", raising=False)
    with patch.object(adapter_mod.psycopg2, "connect", return_value=MagicMock()) as conn:
        built = PostgresAdapter.from_env()
    assert isinstance(built, WarehouseAdapter)
    conn.assert_called_once()
    assert conn.call_args.kwargs["host"] == "h"
    assert conn.call_args.kwargs["dbname"] == "d"
    assert conn.call_args.kwargs["port"] == "5432"


def test_entry_point_registered_and_loads_adapter():
    """Test that the postgres entry point is registered and loads PostgresAdapter."""
    eps = [ep for ep in entry_points(group="continuo_validation.adapters")
           if ep.name == "postgres"]
    assert len(eps) == 1
    assert eps[0].load() is PostgresAdapter


def test_emitted_ddl_parses_as_postgres_dialect():
    """Every emitted statement must be valid postgres SQL per sqlglot."""
    cur = _FakeCursor()
    a = PostgresAdapter(_FakeConn(cur))
    a.build_empty_from_sql("cand", "orders", "SELECT 1 AS id")
    a.clone_empty_from_prod("cand", "analytics", "orders")
    composed = [s for s, _ in cur.calls if not isinstance(s, str)]
    assert len(composed) == 4  # drop+create, drop+create
    for stmt in composed:
        text = _stmt_text_with_idents(stmt)
        assert sqlglot.parse_one(text, dialect="postgres") is not None


def _stmt_text_with_idents(composed) -> str:
    """Render a psycopg2 Composed DB-free: SQL fragments verbatim, Identifiers quoted."""
    from psycopg2 import sql as pg_sql

    parts = []
    for p in composed.seq:
        if isinstance(p, pg_sql.SQL):
            parts.append(p.string)
        elif isinstance(p, pg_sql.Identifier):
            parts.append(".".join(f'"{s}"' for s in p.strings))
        elif isinstance(p, pg_sql.Composed):
            parts.append(_stmt_text_with_idents(p))
    return "".join(parts)
