# continuo-validation-trino

Trino warehouse adapter for the [continuo](https://github.com/carolsimone/continuo)
validation runner. Implements `continuo_validation_contract.port.WarehouseAdapter`;
continuo's harness discovers it through the `continuo_validation.adapters` entry point.

Trino's namespace is `catalog.schema`. The catalog comes from `TRINO_CATALOG` and every
statement is fully qualified, so continuo passes a bare candidate schema name and never
needs to know about catalogs.

## Connection env

| Env | Required | Default | Purpose |
|---|---|---|---|
| `TRINO_HOST` | yes | — | Coordinator host |
| `TRINO_CATALOG` | yes | — | Catalog holding candidate schemas (e.g. `iceberg`) |
| `TRINO_PORT` | no | `8080` | Coordinator port |
| `TRINO_USER` | no | `continuo` | Trino user |
| `TRINO_HTTP_SCHEME` | no | `http` | `http` or `https` |
| `TRINO_PASSWORD` | no | unset | Basic auth; requires `TRINO_HTTP_SCHEME=https` |

The catalog must be backed by a connector that supports schema and table creation
(Iceberg and Hive do). The library is tested live against Iceberg (REST catalog + S3).
