"""Tier-4 image smoke tests: the built image fails structurally, not with tracebacks."""
import os
import subprocess

import pytest

from continuo_validation_core import result

IMAGE = os.environ.get("VALIDATION_IMAGE_UNDER_TEST", "validation-runner-postgres:dev")


def _run(env: dict) -> subprocess.CompletedProcess:
    args = ["docker", "run", "--rm"]
    for k, v in env.items():
        args += ["-e", f"{k}={v}"]
    return subprocess.run(args + [IMAGE], capture_output=True, text=True, timeout=120)


@pytest.mark.image
def test_no_env_exits_2_with_structured_block():
    """Verify missing DBT_TARGET_SCHEMA exits 2, logs to stderr, and emits a block."""
    proc = _run({})
    assert proc.returncode == 2
    assert "missing required env var DBT_TARGET_SCHEMA" in proc.stderr
    assert result.SENTINEL_BEGIN in proc.stdout
    assert "missing required env var DBT_TARGET_SCHEMA" in proc.stdout


@pytest.mark.image
def test_discovery_and_required_env_produce_structured_block():
    """Verify missing postgres env vars produce structured error block."""
    proc = _run({
        "DBT_TARGET_SCHEMA": "_candidate_smoke",
        "TABLE_NAME": "t",
        "VALIDATION_OP": "clone_from_prod",
        "PROD_SCHEMA": "analytics",
    })
    # Discovery finds exactly one adapter (postgres); its required env is absent,
    # so the runner must emit a structured block naming the missing vars and exit 2.
    assert proc.returncode == 2
    assert result.SENTINEL_BEGIN in proc.stdout
    assert "DBT_POSTGRES_HOST" in proc.stdout
    assert "postgres" in proc.stdout
