"""Unit tests for the trino adapter — mock-free.

DDL behavior (ensure_schema, drop_schema, build_empty_from_sql, clone_empty_from_prod,
the connection built by from_env, and DDL validity) is verified against a live Trino +
Iceberg stack in test_integration_trino.py, not with mocked cursors/connections here.
"""
from importlib.metadata import entry_points

from continuo_validation_trino.adapter import TrinoAdapter


def test_required_env_names_host_and_catalog():
    """Test that required_env lists exactly the two mandatory TRINO_* vars."""
    assert TrinoAdapter.required_env() == ["TRINO_HOST", "TRINO_CATALOG"]


def test_entry_point_registered_and_loads_adapter():
    """Test that the trino entry point is registered and loads TrinoAdapter."""
    eps = [ep for ep in entry_points(group="continuo_validation.adapters")
           if ep.name == "trino"]
    assert len(eps) == 1
    assert eps[0].load() is TrinoAdapter
