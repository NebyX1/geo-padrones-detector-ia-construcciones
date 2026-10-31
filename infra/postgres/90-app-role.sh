#!/bin/sh
set -eu
# PostgreSQL bootstrap owns extensions; the application role is never a superuser.
if [ -z "${DATABASE_APP_USER:-}" ]; then
    exit 0
fi
if [ -z "${DATABASE_APP_PASSWORD:-}" ]; then
    echo 'DATABASE_APP_PASSWORD is required when DATABASE_APP_USER is set.' >&2
    exit 1
fi
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
\getenv app_user DATABASE_APP_USER
\getenv app_password DATABASE_APP_PASSWORD
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION', :'app_user', :'app_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname=:'app_user') \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), :'app_user') \gexec
SELECT format('GRANT USAGE, CREATE ON SCHEMA public TO %I', :'app_user') \gexec
SQL
