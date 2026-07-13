# Human review layer

Everything a reviewer needs to audit the result by reading, without rerunning anything. Every file here is real, produced output, regenerable with the commands in the repo `README.md` Reproduce block.

## What is here

- `full_prompt_example.txt`: one complete, real prompt exactly as sent to a model (untruncated), so you can see the full task the model faced.
- `traces/`: curated per-outcome trace files (CATCH / MISS / FALSEFLAG / refusal / budget-exhaustion), one per representative interaction, with the full prompt, full captured reasoning, full visible response, and scored outcome. `traces/README.md` indexes each file and the claim it backs. The idx-56 trace (a round-29 tamper) recurs across several files as a controlled cross-model, cross-rendering contrast on one input.
- `artifacts/`: one proving artifact per pipeline step (Stage-0 self-tests, the example dual renderings, the full metric table, a sample `.eval` excerpt, the zero-new-call replay proof, and the figures). `artifacts/README.md` maps each file to what it proves and which step produced it.

## How to view the raw Inspect logs

The scored `.eval` logs the whole result is derived from live under `data/`. Browse them interactively with the Inspect viewer:

```
inspect view --log-dir data/logs_checkable   # the checkable-rendering result (the 100% headline)
inspect view --log-dir data/logs_raw         # the raw-trace result (the 19% ceiling)
```

Each sample carries the full prompt, full visible output, native reasoning content, and the scorer's stored provenance + metric inputs. Full per-line provenance for the checkable result is in `../results/checkable.jsonl`.
