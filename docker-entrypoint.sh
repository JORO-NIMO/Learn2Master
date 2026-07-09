#!/usr/bin/env sh
set -e

# Initialize the schema (if missing) and seed reference data (once) before
# starting the application server.
python bootstrap.py

exec "$@"
