#!/usr/bin/env bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# Delete openclaw-media-* temporary directories older than a TTL.
#
# The data_intelligence_engine wrapper writes decoded image/video-frame JPGs
# into mktemp -d openclaw-media-XXXXXX directories (under $TMPDIR or /tmp).
# Those files must outlive the wrapper (the agent reads them afterwards), so
# cleanup is time-based, not per-call. response.json is already deleted by the
# wrapper itself; this script removes the whole directory after the TTL.
#
# Usage:
#   cleanup_media.sh [HOURS]     # default 24 hours
#   cleanup_media.sh --dry-run   # list what would be deleted, delete nothing
#
# Cron example (daily at 03:00):
#   0 3 * * * /path/to/skills/knowledgebase/cleanup_media.sh 24
set -euo pipefail

hours=24
dry_run=0
case "${1:-}" in
  --dry-run) dry_run=1 ;;
  "") ;;
  *)
    if [[ ! "$1" =~ ^[1-9][0-9]*$ ]]; then
      echo "Error: HOURS must be a positive integer, or --dry-run." >&2
      exit 2
    fi
    hours="$1"
    ;;
esac

# Whole hours to find's -mmin (minutes since modification).
minutes=$((hours * 60))

# Clean both the wrapper's default location and an agent-specific TMPDIR.
roots=()
for root in "${TMPDIR:-/tmp}" /tmp; do
  [[ -d "$root" ]] || continue
  case " ${roots[*]-} " in
    *" $root "*) ;;
    *) roots+=("$root") ;;
  esac
done

for root in "${roots[@]}"; do
  while IFS= read -r -d '' dir; do
    if [[ "$dry_run" == "1" ]]; then
      printf 'would remove %s\n' "$dir"
    else
      rm -rf -- "$dir"
      printf 'removed %s\n' "$dir"
    fi
  done < <(find "$root" -maxdepth 1 -type d -name 'openclaw-media-*' -mmin +"$minutes" -print0)
done
