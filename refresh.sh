#!/bin/sh
# Daily refresh: pull live FPL data and rebuild the plan dashboard.
# FPL entry 2272028 ("Djed and Buried"). Squad picks only become readable
# after each gameweek deadline, so before GW1 this is ignored and the plan
# is built from scratch rather than from your actual squad.
FPL_ENTRY="${FPL_ENTRY:-2272028}"
# Set once you have joined the work league: export FPL_LEAGUE=<id>
FPL_LEAGUE="${FPL_LEAGUE:-}"
cd "$(dirname "$0")" || exit 1
./.venv/bin/python -m fplm.cli plan \
  --refresh \
  --rivals "${FPL_RIVALS:-19}" \
  --monthly-weight "${FPL_MONTHLY_WEIGHT:-0.75}" \
  ${FPL_ENTRY:+--entry "$FPL_ENTRY"} \
  ${FPL_LEAGUE:+--league "$FPL_LEAGUE"} \
  ${FPL_MINUTES_CSV:+--minutes-csv "$FPL_MINUTES_CSV"} \
  --out plan.html >> refresh.log 2>&1
# Copy to iCloud Drive so the phone picks it up. iOS previews a self-contained HTML
# file straight from the Files app, and iCloud syncs it without any server involved.
ICLOUD="$HOME/Library/Mobile Documents/com~apple~CloudDocs/FPL"
if [ -d "$(dirname "$ICLOUD")" ]; then
  mkdir -p "$ICLOUD"
  cp plan.html "$ICLOUD/plan.html" 2>>refresh.log && echo "  synced to iCloud" >> refresh.log
fi

echo "$(date -u '+%Y-%m-%dT%H:%MZ') refreshed" >> refresh.log
