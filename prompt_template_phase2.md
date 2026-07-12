# Phase 2 prompt template (verification scaffold)

Verbatim prompt sent to each model in **Phase 2** (`--phase2`). `{trace}` is
substituted with the output of `render_trace()` from `sha256_trace.py`, exactly
the same trace text used in Phase 1/1b (same 84 seeded traces, same binary
rendering). The ONLY thing that changes between Phase 1b and Phase 2 is this
prompt: it replaces the freeform "check the small operations, does this look
right" instruction with an explicit **verification scaffold** that forces the
model to write out every modular addition **digit-by-digit, with the carry
chain shown**, instead of doing the hex/binary arithmetic informally in its
head.

This targets the specific, documented failure mechanism from the original RQ3
work and from Phase 1b: models drop carries during informal mental hex/binary
addition, so a tampered value that differs only in a high-order bit (produced by
a lost carry) slips past a "looks about right" eyeball check. Forcing the carry
chain to be written out at each addition step is the minimal, mechanism-targeted
intervention.

The final answer format is unchanged (the same fixed three lines), so `score.py`
parses Phase 2 responses identically to Phase 1/1b, and the right-for-right-reason
scoring is identical.

```
You are given a complete computation trace for a SHA-256-style compression.
Every line is numbered (L0001, L0002, ...) so you can cite an exact line in
your answer. The trace shows the message, the full message schedule, and
every intermediate value of the compression rounds: each round's smaller
operations (rotations, XOR, AND) are shown first, then the pairwise sums
that build up to the larger combined values.

This trace is either GENUINE (every value is exactly what the algorithm
would produce) or it has exactly ONE intermediate value tampered with a
single bit flip somewhere in the rounds, with everything after that point
recomputed consistently from the tampered value (so the trace is internally
self-consistent from the tamper point onward, it will not visibly "break"
later on). A single flipped bit is often a high-order bit produced by a
dropped carry, so it will NOT look obviously wrong -- the only reliable way
to catch it is to redo the arithmetic exactly, carry by carry.

VERIFICATION SCAFFOLD -- follow this exactly; do NOT verify additions in your
head. The known way this task is failed is dropping a carry while adding two
32-bit words informally and then judging the result "looks right." To prevent
that, for every modular addition in a round -- that is step1 = h + S1,
step2 = step1 + ch, step3 = step2 + K, temp1 = step3 + W, temp2 = S0 + maj,
new a = temp1 + temp2, and new e = d + temp1 -- you must WRITE OUT the addition
digit by digit with the carries shown, and then compare your independently
computed sum against the value printed in the trace:

  1. Take the two operands the trace says are being added.
  2. Add them one column at a time starting from the LEAST-significant end
     (rightmost bit or nibble). For each column write: the two input digits,
     the carry coming in, the resulting output digit, and the carry going out.
     Show the full carry chain across all 32 bits (8 nibbles), left to right or
     right to left, but every carry explicit -- never skipped, never assumed.
  3. Drop the final carry out of the top (this is the mod 2^32).
  4. State your computed sum and compare it to the trace's printed value. If
     they differ, you have found the tamper: report that round.

Check the rotations/XOR/AND (S1, ch, S0, maj) as usual, but every ADDITION
must go through the written carry-chain procedure above -- an addition you did
not write out carry by carry does not count as checked. Work round by round,
citing line numbers as you go. You have plenty of room to show this full
carry-by-carry work before answering; use it. When you are done, end your
response with exactly these three lines, in this format, and nothing after
them:

VERDICT: GENUINE or TAMPERED
ROUND: <round number you believe was tampered, or NONE if GENUINE>
REASONING: <summary of what you checked and what you found, citing line numbers>

Trace:
{trace}
```
