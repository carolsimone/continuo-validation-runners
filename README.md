# continuo-validation-runners

Warehouse-engine runner images for [continuo](https://github.com/carolsimone/continuo)
blue/green validation. Each image builds one dbt node as an **empty** table in the
candidate schema — either from its compiled SELECT or by cloning the prod table's
shape — and prints one structured result block that continuo's k8s-controller parses.

## How engine selection works

There is no engine setting. Each image installs `continuo-validation-core` plus
exactly **one** adapter package; core discovers it via the
`continuo_validation.adapters` entry point. Deploying on a given warehouse means
pointing continuo's `VALIDATION_IMAGE` at that engine's image and providing its
connection env (via the `validation.warehouseSecret` Kubernetes Secret).

## Engines

| Image | Required connection env | Optional env | Verification |
|---|---|---|---|
| `ghcr.io/carolsimone/validation-runner-postgres` | `DBT_POSTGRES_HOST`, `DBT_POSTGRES_DB`, `DBT_POSTGRES_USER` | `DBT_POSTGRES_PORT` (5432), `DBT_POSTGRES_PASSWORD` | live (postgres:16 in CI) |

Snowflake, Redshift, BigQuery, Trino, Spark (Thrift), and Databricks adapters are
planned; each will add a row here with its env contract and verification tier.

## Writing your own adapter

Implement `continuo_validation_core.port.WarehouseAdapter` in a package that
declares an entry point in group `continuo_validation.adapters`, then build an
image installing core + your package (see `adapters/postgres/Dockerfile`). Core
enumerates installed entry points at startup and requires exactly one.

## Development

`uv sync --all-packages --all-groups`, then `uv run pytest core/tests
adapters/postgres/tests -m "not integration and not image"`. Live tests need
`docker compose -p validation-runners-it -f docker-compose.integration.yml up -d --wait`.

## License

Apache-2.0
