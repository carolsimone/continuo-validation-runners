"""Unit tests for the postgres adapter — mock-free.

DDL behavior (ensure_schema, drop_schema, build_empty_from_sql, clone_empty_from_prod,
the psycopg2 connection built by from_env, and DDL validity) is verified against a
live postgres engine in test_integration_postgres.py, not with mocked
cursors/connections here.
"""
from importlib.metadata import entry_points

from continuo_validation_postgres.adapter import PostgresAdapter


def test_required_env_names_connection_vars():
    """Test that required_env lists the three mandatory POSTGRES_* vars."""
    assert PostgresAdapter.required_env() == [
        "POSTGRES_HOST", "POSTGRES_DB", "POSTGRES_USER",
    ]


def test_entry_point_registered_and_loads_adapter():
    """Test that the postgres entry point is registered and loads PostgresAdapter."""
    eps = [ep for ep in entry_points(group="continuo_validation.adapters")
           if ep.name == "postgres"]
    assert len(eps) == 1
    assert eps[0].load() is PostgresAdapter
