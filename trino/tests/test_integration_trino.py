"""Tier-2 live tests against Trino + Iceberg REST (docker-compose.integration.yml).

Run the stack first:
    docker compose -f docker-compose.integration.yml --profile trino up -d --wait
"""
import os
import uuid

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
    """A unique candidate schema name, dropped after the test."""
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
