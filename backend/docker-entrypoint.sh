#!/bin/sh
# Apply pending database migrations, then start the server (FR69, FR71).
set -e
python -m app.migrations upgrade
exec "$@"
