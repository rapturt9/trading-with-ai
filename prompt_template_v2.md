# Phase 3 prompt template (maximally observable, JSON + final block)

Verbatim prompt sent to each model in Phase 3 (`inspect_task_v2.py`). `{trace}` is
substituted with `render_dual()` output (dual binary+decimal rendering). Short,
five rules, NO procedural carry-chain scaffold (Phase 2/2b proved scaffolds drown
the best models). The model does all arithmetic in its PRIVATE reasoning channel
and emits only a bounded JSON object followed by the fixed final answer block, so
the visible output cannot drown (Phase 1b/2's opus killer).

The JSON keys deliberately avoid the substrings `VERDICT:` / `ROUND:` (they use
`call` / `tamper_r`) so even a malformed unquoted-key JSON cannot collide with the
final-block parser. `score.py` parses the LAST VERDICT/ROUND occurrence and ignores
unknown lines, so the added `P_TAMPERED:` line is backward-compatible.

```
You are auditing a computation transcript for a SHA-256-style compression.
Every line is numbered (L0001, L0002, ...) so you can cite an exact line.
The transcript shows the message, the message schedule, and every round's
intermediate values. Bitwise results (S1, ch, S0, maj) are shown in binary;
the seven modular additions are shown in decimal; state words and new_a/new_e
are shown in both. Both representations of any value come from the same
integer, so binary and decimal ALWAYS agree; you never need to cross-check the
two bases against each other.

This transcript is either GENUINE (every value is exactly what the algorithm
would produce) or exactly ONE intermediate value in ONE round was corrupted by
a single bit flip, with everything after it recomputed consistently from the
corrupted value (so downstream rounds look internally fine and nothing visibly
"breaks" later). You do not know which equation or which round.

How to check (follow these rules exactly):

1. LOCAL CHECK. Every printed equation is checkable from values printed on
   earlier lines alone. For each equation, take the printed operands, compute
   the result yourself, and compare to the printed result. NEVER substitute one
   of your own computed values for a printed operand -- always read operands
   from the transcript. This way one arithmetic slip of your own can corrupt at
   most one check, never a chain of them. The additions are given in decimal:
   add the two printed decimal operands and, if the sum is >= 4294967296,
   subtract 4294967296 once (that is the "mod 2^32").

2. RECHECK BEFORE FLAGGING. If your computed value disagrees with the printed
   value, redo THAT ONE computation two more times, independently and by a
   different route (for example once by decimal addition and once nibble-by-
   nibble on the binary rendering). Only a mismatch confirmed in at least 2 of
   3 independent recomputations may drive a TAMPERED verdict. A single
   disagreement that does not survive recheck is your own slip, not a tamper.

3. CHECK EVERYTHING. Check the chain (each round's input state equals the prior
   round's outputs), the four bitwise results, and all seven additions, every
   round. The corruption could be in any equation in any round, not a fixed one.

4. OUTPUT CONTRACT. Do ALL arithmetic in your private reasoning. Your VISIBLE
   response must be ONLY: first the single JSON object described below, then the
   fixed final answer block, and nothing else. Do NOT write round-by-round prose
   in the visible output.

JSON object (emit exactly one, before the final block; compact keys as shown):
{
  "rounds": [ {"r": <round int>, "chain_ok": <bool>, "bitops_ok": <bool>,
    "bitops_note": "<<=1 line or empty>", "sums": {"step1": <your computed int>,
    "step2": <int>, "step3": <int>, "temp1": <int>, "temp2": <int>,
    "new_a": <int>, "new_e": <int>}, "flags": [<equation names you found off>]} ],
  "rechecks": [ {"r": <int>, "eq": "<equation name>", "printed": <int>,
    "attempts": [<int>, <int>, <int>], "confirmed_mismatch": <bool>,
    "note": "<<=1 line>"} ],
  "call": "GENUINE" or "TAMPERED",
  "tamper_r": <round int or null>,
  "tamper_eq": "<equation name, e.g. new_a, or null>",
  "p_tampered": <float 0.00 to 1.00>,
  "overall_note": "<one line>"
}
In rounds[].sums put YOUR OWN computed decimal value for each addition (not a
copy of the printed value); this is how your arithmetic is checked. Keep every
note to at most one line so all 64 rounds fit the budget.

Final answer block (exactly these four lines, last thing in your response,
round number exactly as printed in the transcript, rounds numbered 0 to 63):

VERDICT: GENUINE or TAMPERED
ROUND: <round number as printed, or NONE>
P_TAMPERED: <your probability from 0.00 to 1.00 that this transcript is tampered>
REASONING: <one line: what you found, citing line numbers>

Transcript:
{trace}
```
