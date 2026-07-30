#!/bin/sh
# Daily refresh: pull live FPL data and rebuild the plan dashboard.
# Add your entry id once the season starts:  --entry 1234567
cd "$(dirname "$0")" || exit 1
./.venv/bin/python -m fplm.cli plan \
  --refresh \
  --rivals "${FPL_RIVALS:-19}" \
  --monthly-weight "${FPL_MONTHLY_WEIGHT:-0.75}" \
  ${FPL_ENTRY:+--entry "$FPL_ENTRY"} \
  ${FPL_MINUTES_CSV:+--minutes-csv "$FPL_MINUTES_CSV"} \
  --out plan.html >> refresh.log 2>&1
echo "$(date -u '+%Y-%m-%dT%H:%MZ') refreshed" >> refresh.log
