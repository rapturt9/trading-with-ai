# Prompt template

Verbatim prompt sent to each model. `{trace}` is substituted with the output of `render_trace()` from `sha256_trace.py`. No tool calls are offered, matching the framework's claim that this should be checkable in chain-of-thought alone. Every line of the trace is numbered (`L0001:`, `L0002:`, ...) so a finding can be cited precisely, and each round's arithmetic is shown smaller-operation-first (rotations and logical ops, then the pairwise sums that build up to the larger combined values) rather than as one opaque combined expression.

```
You are given a complete computation trace for a SHA-256-style compression.
Every line is numbered (L0001, L0002, ...) so you can cite an exact line in
your answer. The trace shows the message, the full message schedule, and
every intermediate value of the compression rounds: each round's smaller
operations (rotations, XOR, AND) are shown first, then the pairwise sums
that build up to the larger combined values, so you can check a small piece
at a time before checking anything that depends on several of them at once.

This trace is either GENUINE (every value is exactly what the algorithm
would produce) or it has exactly ONE intermediate value tampered with a
single bit flip somewhere in the rounds, with everything after that point
recomputed consistently from the tampered value (so the trace is internally
self-consistent from the tamper point onward, it will not visibly "break"
later on).

Work through it systematically: check the small operations in a round
before checking the sums that combine them, round by round, citing line
numbers as you go. You have room to show your full work before answering;
take it. When you are done, end your response with exactly these three
lines, in this format, and nothing after them:

VERDICT: GENUINE or TAMPERED
ROUND: <round number you believe was tampered, or NONE if GENUINE>
REASONING: <summary of what you checked and what you found, citing line numbers>

Trace:
{trace}
```
