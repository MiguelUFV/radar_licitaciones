#!/bin/bash
# Crea la base de datos de n8n junto a la del radar (la principal la crea la propia imagen).
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    SELECT 'CREATE DATABASE ' || quote_ident('${POSTGRES_DB_N8N}')
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${POSTGRES_DB_N8N}')\gexec
EOSQL
