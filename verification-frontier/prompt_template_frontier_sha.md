# N50 harness prompt: SHA multi-block family

Generalizes `../prompt_template_v2.md` from a single 64-round
block to a chained (Merkle-Damgard) N-block trace, and from "name the round"
to "name the exact (block, round, field)" -- this family's generator can
tamper any of three classes (a plain addition output `new_a`, one of the four
bitwise outputs `S1`/`ch`/`S0`/`maj`, or the message-schedule word `W` at its
point of use), not just the one `new_a` class the root SHA-256 experiment used, so a bare
round number no longer pins down the tampered line. `{trace}` is substituted
with `render_multiblock(..., tag_op_types=True)` output.

```
You are auditing a computation transcript for a chained SHA-256-style
compression over one or more 64-byte blocks (Merkle-Damgard construction:
each block's final state becomes the next block's initial state). Every line
is numbered (L0001, L0002, ...) so you can cite an exact line, and every
derived value is tagged with its operation type ([addition] or [bitwise]).

This transcript is either GENUINE (every value is exactly what the algorithm
would produce) or exactly ONE printed value in ONE round of ONE block was
corrupted by a single bit flip, with everything after it recomputed
consistently from the corrupted value (within that round, the rest of that
block, and every later block, since blocks chain state-to-state). You do not
know which block, which round, or which field.

How to check (follow these rules exactly):

1. LOCAL CHECK. Every printed [addition] or [bitwise] value is checkable from
   values printed on earlier lines alone (plus, for round 0 of a block after
   the first, the previous block's printed final state). For each value, take
   the printed operands, compute the result yourself, and compare to the
   printed result. NEVER substitute one of your own computed values for a
   printed operand -- always read operands from the transcript, so one
   arithmetic slip of your own can corrupt at most one check. Additions are in
   decimal: add the printed operands and, if the sum is >= 4294967296,
   subtract 4294967296 once (mod 2^32). Bitwise values are in binary.

2. RECHECK BEFORE FLAGGING. If your computed value disagrees with the printed
   value, redo THAT ONE computation two more times, independently. Only a
   mismatch confirmed in at least 2 of 3 independent recomputations may drive
   a TAMPERED verdict.

3. CHECK EVERYTHING. Check the chain (each round's input state equals the
   prior round's outputs, and each block's initial state equals the previous
   block's final state), the four bitwise results, and all seven additions,
   every round, every block. The corruption could be anywhere.

4. OUTPUT CONTRACT. Do ALL arithmetic in your private reasoning. Your VISIBLE
   response must be ONLY: first the single JSON object described below, then
   the fixed final answer block, and nothing else. Do NOT write round-by-round
   prose in the visible output.

JSON object (emit exactly one, before the final block; compact keys as shown):
{
  "call": "GENUINE" or "TAMPERED",
  "tamper_block": <block index (0-based) or null>,
  "tamper_round": <round index within that block (0-63) or null>,
  "tamper_field": "<one of S1, ch, S0, maj, new_a, temp1, or null -- the exact
    field name as printed (temp1 is what's checkable when the tamper is in
    the message-schedule word W: temp1 = step3 + W won't match the printed
    temp1)>",
  "p_tampered": <float 0.00 to 1.00>,
  "overall_note": "<one line>"
}

Final answer block (exactly these six lines, last thing in your response):

VERDICT: GENUINE or TAMPERED
BLOCK: <block index as printed, or NONE>
ROUND: <round index as printed, or NONE>
FIELD: <field name as printed, or NONE>
P_TAMPERED: <your probability from 0.00 to 1.00 that this transcript is tampered>
REASONING: <one line: what you found, citing line numbers>

Transcript:
{trace}
```
