# Quarantined: pre-verdict-leak-fix ECDSA pilot logs

Moved here 2026-07-12 per the round-2 audit (relayed by the team lead). These
4 `.eval` files were produced by `ecdsa_trace.py`'s small-curve renderer BEFORE
the verdict-leak fix (the renderer used to print `Final comparison ...
v == r ? {trace['valid']}` as its last line, a direct True/False readout of
the genuine/tampered verdict). All 4 still contain that leaked string and
carry no `renderer_version` metadata key (added only in the fixed renderer).

| File | Family | Model | n |
|---|---|---|---|
| `2026-07-12T17-32-07+00-00_verification-frontier_Cg4xhDmme3cF6xy7YaN7yW.eval` | ecdsa | openai/gpt-5 | 4 |
| `2026-07-12T18-09-23+00-00_verification-frontier_o3KiXC2fmfWUyY9aQrUsVd.eval` | ecdsa | anthropic/claude-opus-4.6 | 4 |
| `2026-07-12T19-19-28+00-00_verification-frontier_VW9e5sVkMMpzZWeCKUK7cG.eval` | ecdsa | openai/gpt-4o | 8 |
| `2026-07-12T19-19-32+00-00_verification-frontier_CrWDekaMctfRrHpAHxfZRB.eval` | ecdsa | openai/o3 | 8 |

**Status per round-1's tag (`location-metric-only, verdict leak`)**: the
`TP_r4r` exact-location numbers in these logs were independently re-scored by
`frontier-builder` and confirmed not inflated (naming the precise corrupted
line isn't derivable from a leaked boolean). **Superseded by round 2**: even
location metrics from pre-fix data are now treated as provisional, since
knowing the verdict for free could plausibly raise a model's search
persistence on the location-finding sub-task too (a channel round 1's ruling
didn't rule out). These 4 conditions are being regenerated at the same `n` on
the fixed renderer (`RENDERER_VERSION = "v2-no-verdict-leak-2026-07-12"`);
once a condition's rerun lands, `plan.md`/`README.md` tag it "superseded by
post-fix rerun" and the rerun's log (in `logs_pilot/` or `logs_live/`,
un-quarantined) becomes the citable data for that condition.

These 4 files are kept, not deleted, for provenance -- do not delete.
