# continuo-validation-runners

A library-only monorepo of warehouse-engine adapters for
[continuo](https://github.com/carolsimone/continuo) blue/green validation. Each
top-level folder is a PyPI library depending on the published
`continuo-validation-contract` package (the `WarehouseAdapter` port), proven
against a real engine via `docker-compose.integration.yml`. There are no
Dockerfiles or runner images here — continuo's `validation-runner` harness
installs one engine library per slim image at build time.

## How engine selection works

Each library implements `continuo_validation_contract.port.WarehouseAdapter`
and declares an entry point in group `continuo_validation.adapters`. continuo's
harness installs the harness plus exactly **one** engine library into an image
and discovers the adapter via that entry point at startup. Deploying on a given
warehouse means pointing continuo's `VALIDATION_IMAGE` at that engine's image
and providing its connection env (via the `validation.warehouseSecret`
Kubernetes Secret).

## Libraries

| Library | Import package | Required connection env | Optional env | Verification |
|---|---|---|---|---|
| `continuo-validation-postgres` | `continuo_validation_postgres` | `POSTGRES_HOST`, `POSTGRES_DB`, `POSTGRES_USER` | `POSTGRES_PORT` (5432), `POSTGRES_PASSWORD` (empty) | live (postgres:16 in CI) |

Snowflake, Redshift, BigQuery, Trino, Spark (Thrift), and Databricks adapters
are planned; each will add a row here with its env contract and verification
tier.

## Writing your own adapter

Implement `continuo_validation_contract.port.WarehouseAdapter` (from the
published `continuo-validation-contract` package) in a new top-level folder
that declares an entry point in group `continuo_validation.adapters`, and add a
`docker-compose.integration.yml` service to prove it against a real engine. The
continuo harness enumerates installed entry points at startup and requires
exactly one.

stdout is a parsed channel: continuo's harness prints one sentinel-framed
result block as its last stdout line. Your adapter must log diagnostics with
the stdlib `logging` module (captured from the pod log), never print or
otherwise write to stdout, and must never emit the
`===CONTINUO_VALIDATION_RESULT_BEGIN/END===` marker strings itself.

## Development

`uv sync --all-packages --all-groups`, then `uv run pytest postgres/tests -m
"not integration"`. Live tests need `docker compose -p validation-runners-it -f
docker-compose.integration.yml up -d --wait`.

The `continuo-validation-contract` dependency currently resolves from TestPyPI
until it is published to real PyPI — set both env vars before `uv sync`/`uv
run`:

```bash
export UV_EXTRA_INDEX_URL=https://test.pypi.org/simple/
export UV_INDEX_STRATEGY=unsafe-best-match  # some dev tools also exist on TestPyPI
```

## Publishing

Each library publishes independently via OIDC Trusted Publishing (no stored
tokens) on a `<library>-v*` tag — see `.github/workflows/publish-pypi.yml`. Tag
suffix `-test` (e.g. `postgres-v0.1.0-test1`) publishes to TestPyPI; otherwise
to real PyPI.

## License

Apache-2.0
