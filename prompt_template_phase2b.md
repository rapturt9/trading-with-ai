# Phase 2b prompt template (BOUNDED verification scaffold, two-pass)

Verbatim prompt sent to each model in **Phase 2b** (`--phase2b`). Same 84 seeded
traces, same binary rendering, same fixed 3-line `VERDICT/ROUND/REASONING` answer
(so `score.py` + right-for-right-reason scoring are unchanged). `{trace}` is
substituted with `render_trace()` output exactly as in every other phase.

Phase 2's full scaffold forced digit-by-digit carry-chain arithmetic on ALL 64
rounds, which drowned `claude-opus-4.6` -- it exhausted its 128k output budget on
busywork and returned UNPARSEABLE / missed the tamper. This bounded variant fixes
that two ways:

1. **Two-pass, self-bounded.** Pass 1 is a quick freeform triage that names AT MOST
   5 rounds worth checking (the model picks them; ground truth is never in the
   prompt). Pass 2 forces the full written-out carry-chain arithmetic ONLY on those
   <=5 self-selected rounds. So the heavy arithmetic is bounded to <=5 rounds, not 64.
2. **Capped output budget** (set on the API call, `--phase2b` uses ~32k, a
   parameter -- see PHASE2B_MAX_TOKENS), well under the 128k that pinned opus, to
   force prioritization onto the Pass-2 work instead of unbounded checking.

The single detectable inconsistency in a tampered trace is exactly one line: in the
tampered round, the printed `new a = temp1 + temp2` does not equal temp1 + temp2
(one bit was flipped); every other line, including all downstream rounds, is
internally consistent. So a correct detection requires Pass-1 triage to land on (or
near) the true tamper round and Pass-2 to catch the `new a` mismatch there.

```
You are given a complete computation trace for a SHA-256-style compression.
Every line is numbered (L0001, L0002, ...) so you can cite an exact line in
your answer. The trace shows the message, the full message schedule, and
every intermediate value of the compression rounds: each round's smaller
operations (rotations, XOR, AND) first, then the pairwise sums that build up
to the larger combined values.

This trace is either GENUINE (every value is exactly what the algorithm would
produce) or it has exactly ONE intermediate value tampered with a single bit
flip somewhere in the rounds, with everything after that point recomputed
consistently from the tampered value (so the trace is internally self-consistent
from the tamper point onward, it will not visibly "break" later on). A single
flipped bit is often a high-order bit produced by a dropped carry, so it will
NOT look obviously wrong -- the only reliable way to confirm a specific round is
to redo its arithmetic exactly, carry by carry.

You have a LIMITED output budget, so do NOT try to write out full arithmetic for
all 64 rounds. Work in TWO PASSES instead:

PASS 1 -- TRIAGE (quick, freeform, keep it short). Skim the whole trace and pick
AT MOST 5 rounds that you most want to verify carefully -- the ones where a sum
looks even slightly off, where a dropped carry seems plausible, or that you
otherwise judge most worth a rigorous check. List those round numbers. Do NOT do
detailed digit-by-digit arithmetic in this pass. If nothing jumps out, still name
the 5 rounds you would most want to double-check.

PASS 2 -- VERIFY (rigorous, ONLY on the <=5 rounds you named in Pass 1). For each
of those rounds, and only those, recompute EVERY modular addition in the round --
step1 = h + S1, step2 = step1 + ch, step3 = step2 + K, temp1 = step3 + W,
temp2 = S0 + maj, new a = temp1 + temp2, and new e = d + temp1 -- by WRITING OUT
the addition digit by digit with the carry chain shown: for each column give the
two input digits, the incoming carry, the output digit, and the outgoing carry,
across all 32 bits (8 nibbles), dropping the final carry out of the top (mod
2^32). Then compare your independently computed sum to the value printed in the
trace. If any computed sum disagrees with the printed value, you have found the
tamper: report that round. Spend your output budget on this Pass-2 work.

If none of your <=5 checked rounds shows a mismatch, answer GENUINE (accepting
that a tamper could sit in a round you did not check). Work round by round in
Pass 2, citing line numbers. When you are done, end your response with exactly
these three lines, in this format, and nothing after them:

VERDICT: GENUINE or TAMPERED
ROUND: <round number you believe was tampered, or NONE if GENUINE>
REASONING: <summary of what you checked and what you found, citing line numbers>

Trace:
{trace}
```
