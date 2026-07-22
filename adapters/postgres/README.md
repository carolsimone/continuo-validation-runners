# continuo-validation-postgres

Postgres adapter for the continuo validation runner. Connection env:
`DBT_POSTGRES_HOST`, `DBT_POSTGRES_DB`, `DBT_POSTGRES_USER` (required);
`DBT_POSTGRES_PORT` (default 5432), `DBT_POSTGRES_PASSWORD` (default empty).
Verification tier: live integration tests against postgres:16.
