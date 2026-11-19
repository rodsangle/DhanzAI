#!/bin/sh
# Fresh local database with Supabase stand-ins, migrations and demo data.
set -e
su postgres -c "psql -h /tmp -p 5499 -d postgres -qc 'drop database if exists rodrech with (force)' -c 'create database rodrech'"
cd "$(dirname "$0")/../.."
export DATABASE_URL=postgres://postgres@localhost:5499/rodrech
node scripts/db.mjs stubs >/dev/null && node scripts/db.mjs migrate >/dev/null && node scripts/db.mjs seed-demo >/dev/null
rm -rf .data
echo "db reset"
