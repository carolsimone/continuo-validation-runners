"""Unit tests for the s3 module — no boto3 network calls."""
import pytest

from continuo_validation_core import s3


def test_parse_s3_uri_splits_bucket_and_key():
    """A well-formed s3:// URI splits into its bucket and key parts."""
    assert s3.parse_s3_uri("s3://bucket/a/b.sql") == ("bucket", "a/b.sql")


@pytest.mark.parametrize("uri", ["http://x/y", "s3://bucket-only", "s3://bucket/", "s3://"])
def test_parse_s3_uri_rejects_invalid(uri):
    """Non-s3 schemes, and URIs missing a bucket or key, raise ValueError."""
    with pytest.raises(ValueError):
        s3.parse_s3_uri(uri)


def test_require_env_exits_2_when_missing(monkeypatch, caplog):
    """A missing required env var exits with code 2 and names itself in the log."""
    monkeypatch.delenv("SOME_VAR", raising=False)
    with pytest.raises(SystemExit) as exc:
        s3.require_env("SOME_VAR", caller="validation_runner")
    assert exc.value.code == 2
    assert "SOME_VAR" in caplog.text
