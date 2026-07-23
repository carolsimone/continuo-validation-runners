# continuo-validation-postgres

Postgres warehouse-adapter library for continuo's validation runner. Implements
`continuo_validation_contract.port.WarehouseAdapter` (from the published
`continuo-validation-contract` package) and registers itself under entry-point
group `continuo_validation.adapters` as `postgres`.

Connection env: `POSTGRES_HOST`, `POSTGRES_DB`, `POSTGRES_USER` (required);
`POSTGRES_PORT` (default 5432), `POSTGRES_PASSWORD` (default empty).
Verification tier: live integration tests against postgres:16.
