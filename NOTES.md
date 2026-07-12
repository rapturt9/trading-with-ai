# Notes on this package

## Excluded Inspect log (over GitHub's 100 MB file limit)

One `.eval` log from the max-effort raw-trace run exceeds GitHub's hard 100 MB per-file
limit and is therefore not committed:

- `logs_inspect/2026-07-08T16-55-30+00-00_sha256-tamper-detection_XWcxk4G2WN9oZ4msAgcUDk.eval` (107,165,113 bytes, ~102 MB)

Every other `.eval` log (all of `logs_inspect_v2/`, the rest of `logs_inspect/`)
is committed. The excluded file is regenerable via the Reproduce commands in
`README.md`. Note that re-running the eval makes real, paid API calls; it is not
free like the cache replay. The committed `cache/` and `results*.jsonl` already
contain the underlying per-call inputs and outcomes, so the excluded `.eval` is
a viewer convenience, not the source of any headline number.
