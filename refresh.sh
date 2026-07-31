#!/bin/sh
# Daily refresh: pull live FPL data and rebuild the plan dashboard.
# FPL entry 2272028 ("Djed and Buried"). Squad picks only become readable
# after each gameweek deadline, so before GW1 this is ignored and the plan
# is built from scratch rather than from your actual squad.
FPL_ENTRY="${FPL_ENTRY:-2272028}"
# Space-separated for several leagues: export FPL_LEAGUE="123456 789012"
FPL_LEAGUE="${FPL_LEAGUE:-}"
cd "$(dirname "$0")" || exit 1
./.venv/bin/python -m fplm.cli plan \
  --refresh \
  --rivals "${FPL_RIVALS:-19}" \
  --monthly-weight "${FPL_MONTHLY_WEIGHT:-0.75}" \
  ${FPL_ENTRY:+--entry "$FPL_ENTRY"} \
  ${FPL_LEAGUE:+--league $FPL_LEAGUE} \
  ${FPL_MINUTES_CSV:+--minutes-csv "$FPL_MINUTES_CSV"} \
  --out plan.html >> refresh.log 2>&1
# Copy to iCloud Drive so the phone picks it up. iOS previews a self-contained HTML
# file straight from the Files app, and iCloud syncs it without any server involved.
ICLOUD="$HOME/Library/Mobile Documents/com~apple~CloudDocs/FPL"
if [ -d "$(dirname "$ICLOUD")" ]; then
  mkdir -p "$ICLOUD"
  # Stream the bytes rather than cp: plan.html carries extended attributes that
  # iCloud Drive refuses, and cp fails with "Operation not permitted" trying to
  # preserve them. Redirection copies content only.
  # Remove before writing. A file previously created by a process holding Full Disk
  # Access cannot be overwritten by this agent, but it CAN create a fresh one.
  rm -f "$ICLOUD/plan.html" 2>/dev/null
  if cat plan.html > "$ICLOUD/plan.html" 2>>refresh.log; then
    echo "  synced to iCloud ($(wc -c < "$ICLOUD/plan.html" | tr -d ' ') bytes)" >> refresh.log
  else
    echo "  !! iCloud sync FAILED" >> refresh.log
  fi
fi

echo "$(date -u '+%Y-%m-%dT%H:%MZ') refreshed" >> refresh.log
