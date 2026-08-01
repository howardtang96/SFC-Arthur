#!/bin/bash
# Sequential Layer 2: corporations first, then individuals.
# Auto-restarts on crash; run_layer2.py is resumable via its checkpoint CSV.
cd "$(dirname "$0")"

for role in corporation individual; do
  for attempt in 1 2 3 4 5 6 7 8 9 10; do
    echo "=== $(date) starting $role attempt $attempt ==="
    python -u run_layer2.py "$role" >> "../output/layer2_${role}.log" 2>&1
    if grep -q "LAYER2 $role DONE" "../output/layer2_${role}.log"; then
      echo "=== $role COMPLETE ==="
      break
    fi
    echo "=== $role crashed, retrying in 30s ==="
    sleep 30
  done
done
echo "=== ALL LAYER2 COMPLETE $(date) ==="
