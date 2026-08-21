#!/usr/bin/env bash
# Smoke runner for evaluate_kronos_ic.py
# Usage: bash scripts/_smoke/run_smoke.sh
set -euo pipefail

ROOT="/data/AgentLink/Skills/Chinese_Stock_Updating/Kronos/Kronos"
SMOKE="${ROOT}/scripts/_smoke"
PY="${HOME}/miniconda3/envs/kronos/bin/python"

cd "${ROOT}"
${PY} "${ROOT}/scripts/evaluate_kronos_ic.py" \
    --start 2024-09-01 --end 2024-12-31 \
    --rebalance-freq W \
    --pick-source csv \
    --csv-pick-file "${SMOKE}/picks.csv" \
    --csv-dir "${SMOKE}" \
    --lookback 256 --pred-len 5 --realise-horizon 5 \
    --top-k 3 --sample-count 2 \
    --device cuda --max-context 512 \
    --price-limit 0.10 \
    --run-tag _smoke_kronos_csv