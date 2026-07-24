"""Tier-2 live tests against Trino + Iceberg REST (docker-compose.integration.yml).

Run the stack first:
    docker compose -f docker-compose.integration.yml --profile trino up -d --wait
"""
import os
import uuid

from concurrent.futures import ThreadPoolExecutor

import pytest

from continuo_validation_trino.adapter import TrinoAdapter

TRINO_ENV = {
    "TRINO_HOST": "localhost",
    "TRINO_PORT": os.environ.get("VR_IT_TRINO_PORT", "18080"),
    "TRINO_USER": "continuo",
    "TRINO_CATALOG": "iceberg",
    "TRINO_HTTP_SCHEME": "http",
}


def _adapter() -> TrinoAdapter:
    """Build an adapter from the live stack's connection env."""
    for key, value in TRINO_ENV.items():
        os.environ[key] = value
    os.environ.pop("TRINO_PASSWORD", None)
    return TrinoAdapter.from_env()


def _schema_exists(adapter: TrinoAdapter, schema: str) -> bool:
    rows = adapter._execute("SHOW SCHEMAS FROM iceberg")
    return any(row[0] == schema for row in rows)


@pytest.fixture()
def candidate_schema():
    """Yield a unique candidate schema name, dropped after the test."""
    schema = f"_candidate_it_{uuid.uuid4().hex[:8]}"
    yield schema
    cleanup = _adapter()
    cleanup.drop_schema(schema)
    cleanup.close()


@pytest.mark.integration
def test_ensure_schema_creates_and_is_idempotent(candidate_schema):
    """ensure_schema creates the schema; a second call succeeds unchanged."""
    a = _adapter()
    a.ensure_schema(candidate_schema)
    assert _schema_exists(a, candidate_schema)
    a.ensure_schema(candidate_schema)  # must not raise
    assert _schema_exists(a, candidate_schema)
    a.close()


@pytest.mark.integration
def test_drop_schema_removes_schema_containing_tables(candidate_schema):
    """Trino has no DROP SCHEMA CASCADE: drop_schema must drop the tables first."""
    a = _adapter()
    a.ensure_schema(candidate_schema)
    # Two tables, created directly so this test does not depend on the build methods.
    for table in ("t_one", "t_two"):
        a._execute(
            f'CREATE TABLE iceberg."{candidate_schema}"."{table}" AS '
            f"SELECT 1 AS id WITH NO DATA"
        )
    a.drop_schema(candidate_schema)
    assert not _schema_exists(a, candidate_schema)
    a.close()


@pytest.mark.integration
def test_drop_schema_on_absent_schema_is_a_noop():
    """Teardown must never fail a release for an already-clean warehouse."""
    a = _adapter()
    a.drop_schema(f"_candidate_missing_{uuid.uuid4().hex[:8]}")  # must not raise
    a.close()


def _columns(adapter: TrinoAdapter, schema: str, table: str) -> list[tuple[str, str]]:
    rows = adapter._execute(
        "SELECT column_name, data_type FROM iceberg.information_schema.columns "
        f"WHERE table_schema = '{schema}' AND table_name = '{table}' "
        "ORDER BY ordinal_position"
    )
    return [(row[0], row[1]) for row in rows]


def _count(adapter: TrinoAdapter, schema: str, table: str) -> int:
    rows = adapter._execute(f'SELECT count(*) FROM iceberg."{schema}"."{table}"')
    return int(rows[0][0])


@pytest.fixture()
def prod_table():
    """Yield a prod-like schema with one populated table; dropped after the test."""
    schema = f"_prod_it_{uuid.uuid4().hex[:8]}"
    a = _adapter()
    a.ensure_schema(schema)
    a._execute(
        f'CREATE TABLE iceberg."{schema}"."src_table" AS '
        "SELECT * FROM (VALUES (1, 'a'), (2, 'b')) AS t(id, name)"
    )
    a.close()
    yield schema
    cleanup = _adapter()
    cleanup.drop_schema(schema)
    cleanup.close()


@pytest.mark.integration
def test_build_empty_from_sql_live(candidate_schema, prod_table):
    """Build an empty candidate table shaped by a compiled SELECT."""
    a = _adapter()
    a.ensure_schema(candidate_schema)
    a.build_empty_from_sql(
        candidate_schema, "built",
        f'SELECT id, name FROM iceberg."{prod_table}"."src_table"',
    )
    assert _columns(a, candidate_schema, "built") == [("id", "integer"), ("name", "varchar")]
    assert _count(a, candidate_schema, "built") == 0
    a.close()


@pytest.mark.integration
def test_build_is_rerun_idempotent(candidate_schema, prod_table):
    """Building the same table twice drops and recreates instead of failing."""
    a = _adapter()
    a.ensure_schema(candidate_schema)
    for _ in range(2):
        a.build_empty_from_sql(
            candidate_schema, "rerun",
            f'SELECT id FROM iceberg."{prod_table}"."src_table"',
        )
    assert _count(a, candidate_schema, "rerun") == 0
    a.close()


@pytest.mark.integration
def test_clone_empty_from_prod_live(candidate_schema, prod_table):
    """Clone an empty candidate table shaped like the prod table."""
    a = _adapter()
    a.ensure_schema(candidate_schema)
    a.clone_empty_from_prod(candidate_schema, prod_table, "src_table")
    assert _columns(a, candidate_schema, "src_table") == [
        ("id", "integer"), ("name", "varchar"),
    ]
    assert _count(a, candidate_schema, "src_table") == 0
    a.close()


@pytest.mark.integration
def test_drop_schema_removes_schema_containing_views(candidate_schema):
    """Trino's SHOW TABLES lists views too; drop_schema must remove them as well."""
    a = _adapter()
    a.ensure_schema(candidate_schema)
    a._execute(
        f'CREATE TABLE iceberg."{candidate_schema}"."base_t" AS SELECT 1 AS id WITH NO DATA'
    )
    a._execute(
        f'CREATE VIEW iceberg."{candidate_schema}"."v_one" AS '
        f'SELECT id FROM iceberg."{candidate_schema}"."base_t"'
    )
    a.drop_schema(candidate_schema)
    assert not _schema_exists(a, candidate_schema)
    a.close()


@pytest.mark.integration
def test_ensure_schema_concurrent_callers_all_succeed():
    """Parallel root validation nodes race CREATE SCHEMA; every caller must succeed.

    The Iceberg REST metastore can report the loser of the create race as a
    query-level error rather than a user error; ensure_schema must treat any
    outcome where the schema ends up existing as success.
    """
    for _ in range(4):
        schema = f"_candidate_race_{uuid.uuid4().hex[:8]}"
        adapters = [_adapter() for _ in range(8)]
        try:
            with ThreadPoolExecutor(max_workers=8) as pool:
                futures = [pool.submit(a.ensure_schema, schema) for a in adapters]
                for future in futures:
                    future.result()  # raises if any caller failed
            assert _schema_exists(adapters[0], schema)
        finally:
            for a in adapters:
                a.close()
            cleanup = _adapter()
            cleanup.drop_schema(schema)
            cleanup.close()
