#!/usr/bin/env bash
set -euo pipefail
cd /app/backend
# Free Render instances have no pre-deploy command or shell. Fail closed before
# listening if configuration, migrations, or explicitly enabled seeding fail.
printf '[startup] Starting database bootstrap.\n'
python -u /app/deploy/database.py bootstrap
printf '[startup] Database bootstrap process exited successfully; starting application services.\n'
exec bash run_services.sh
