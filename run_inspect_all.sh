#!/bin/bash
# Runs the 5 live-run models' full 84-sample Inspect port in parallel
# background processes (one per model, so a slow claude-opus-4.6 call
# doesn't block the fast models), matching run_experiment.py's
# interleaved-thread-pool intent via OS-level process parallelism instead.
set -a
source /home/ram/obsidian/.env
set +a
cd /home/ram/obsidian/experiments/260706-credible-deals-polish/rq3-replication

MODELS=(
  "openai/gpt-4o"
  "openai/o3"
  "openai/gpt-5"
  "anthropic/claude-opus-4.6"
  "openai/gpt-5.5"
)

for m in "${MODELS[@]}"; do
  logfile="logs_inspect_run_$(echo "$m" | tr '/' '_').log"
  inspect eval inspect_task.py \
    --model "openrouter/$m" \
    -T "model_key=$m" \
    --log-dir logs_inspect \
    --max-connections 16 \
    --max-retries 6 \
    --display plain \
    > "$logfile" 2>&1 &
done

wait
echo "ALL_INSPECT_RUNS_DONE"
