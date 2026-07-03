#!/usr/bin/env bash
# Run all Orbit tests with plain python3 (stdlib only, no network). Exit non-zero on any failure.
set -u
here="$(cd "$(dirname "$0")" && pwd -P)"
fail=0
for t in "$here"/test_*.py; do
  [ -f "$t" ] || continue
  echo "── $(basename "$t")"
  if ! python3 "$t"; then fail=1; fi
done
# The coherence gate (added in Phase 5) runs too, if present.
if [ -f "$here/../scripts/check-coherence.py" ]; then
  echo "── check-coherence.py"
  if ! python3 "$here/../scripts/check-coherence.py"; then fail=1; fi
fi
[ "$fail" = 0 ] && echo "ALL TESTS PASS" || echo "TESTS FAILED"
exit "$fail"
