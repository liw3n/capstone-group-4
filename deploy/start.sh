#!/usr/bin/env bash
set -euo pipefail
cd /app/backend
# Free Render instances have no pre-deploy command or shell. Fail closed before
# listening if configuration, migrations, or explicitly enabled seeding fail.
python /app/deploy/database.py bootstrap
exec bash run_services.sh
