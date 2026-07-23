"""Tier-2 live tests against postgres:16 (docker-compose.integration.yml)."""
import concurrent.futures
import os
import uuid

import psycopg2
import pytest

from continuo_validation_postgres.adapter import PostgresAdapter

PG = dict(
    host="localhost",
    port=os.environ.get("VR_IT_PG_PORT", "15433"),
    dbname="warehouse",
    user="continuo",
    password="continuo",
)


def _conn():
    return psycopg2.connect(**PG)


@pytest.fixture()
def prod_table():
    """Create prod_it.src_table with two rows; drop candidate leftovers."""
    conn = _conn()
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS prod_it")
        cur.execute("DROP TABLE IF EXISTS prod_it.src_table")
        cur.execute("CREATE TABLE prod_it.src_table (id int, name text)")
        cur.execute("INSERT INTO prod_it.src_table VALUES (1, 'a'), (2, 'b')")
    yield "prod_it"
    conn.close()


def _columns(schema: str, table: str) -> list[tuple[str, str]]:
    conn = _conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position",
            (schema, table),
        )
        cols = cur.fetchall()
    conn.close()
    return cols


def _count(schema: str, table: str) -> int:
    conn = _conn()
    with conn.cursor() as cur:
        cur.execute(f'SELECT count(*) FROM "{schema}"."{table}"')
        n = cur.fetchone()[0]
    conn.close()
    return n


def _schema_exists(schema: str) -> bool:
    conn = _conn()
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM information_schema.schemata WHERE schema_name=%s", (schema,))
        found = cur.fetchone() is not None
    conn.close()
    return found


@pytest.mark.integration
def test_build_empty_from_sql_live(prod_table):
    """Build an empty candidate table shaped by a compiled SELECT."""
    a = PostgresAdapter(_conn())
    a.ensure_schema("_candidate_it")
    a.build_empty_from_sql("_candidate_it", "built", "SELECT id, name FROM prod_it.src_table")
    a.close()
    assert _columns("_candidate_it", "built") == [("id", "integer"), ("name", "text")]
    assert _count("_candidate_it", "built") == 0


@pytest.mark.integration
def test_clone_empty_from_prod_live(prod_table):
    """Clone an empty candidate table shaped like the prod table."""
    a = PostgresAdapter(_conn())
    a.ensure_schema("_candidate_it")
    a.clone_empty_from_prod("_candidate_it", "prod_it", "src_table")
    a.close()
    assert _columns("_candidate_it", "src_table") == [("id", "integer"), ("name", "text")]
    assert _count("_candidate_it", "src_table") == 0


@pytest.mark.integration
def test_build_is_rerun_idempotent(prod_table):
    """Building the same table twice drops and recreates instead of failing."""
    a = PostgresAdapter(_conn())
    a.ensure_schema("_candidate_it")
    for _ in range(2):  # second run must drop-and-recreate, not fail
        a.build_empty_from_sql("_candidate_it", "rerun", "SELECT id FROM prod_it.src_table")
    a.close()
    assert _count("_candidate_it", "rerun") == 0


@pytest.mark.integration
def test_drop_schema_removes_it_and_is_idempotent(prod_table):
    """drop_schema deletes the schema and its tables; dropping again is a no-op."""
    schema = f"_candidate_drop_{uuid.uuid4().hex[:8]}"
    a = PostgresAdapter(_conn())
    a.ensure_schema(schema)
    a.build_empty_from_sql(schema, "t", "SELECT id FROM prod_it.src_table")
    assert _schema_exists(schema)
    a.drop_schema(schema)
    assert not _schema_exists(schema)
    a.drop_schema(schema)  # absent schema → no error
    a.close()
    assert not _schema_exists(schema)


@pytest.mark.integration
def test_ensure_schema_race_all_callers_succeed():
    """Concurrent ensure_schema callers on the same schema all succeed."""
    schema = f"_candidate_race_{uuid.uuid4().hex[:8]}"

    def _one() -> bool:
        a = PostgresAdapter(_conn())
        a.ensure_schema(schema)
        a.close()
        return True

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        assert all(f.result() for f in [ex.submit(_one) for _ in range(8)])
