# N50 harness prompt: small-curve ECDSA family

`{trace}` is substituted with `ecdsa_trace.render_trace(...)` output. Location
is named as (section, op_idx, step) matching `local_consistency_report`'s own
tuple format exactly, so scoring never has to reinterpret free text.
`{recheck_reminder}` is substituted with either "" (base variant) or one extra
sentence (see prompt_variant="recheck_reminder" in inspect_task_frontier.py) --
the rendering-optimization pass's variant (b): a prompt-level nudge, not a
rendering change, per proposal.md.

```
You are auditing a computation transcript for a small-curve ECDSA signature
VERIFICATION (not signing). Every line is numbered (L0001, L0002, ...) so you
can cite an exact line, and every derived value is tagged with its operation
type: [addition], [multiplication], [reduction], or [inverse-check].

The transcript traces, in order: the header (w = s^-1 mod n, then u1 = z*w mod
n, u2 = r*w mod n), two double-and-add scalar-multiplication ladders (ladder 1
computes u1*G, ladder 2 computes u2*Q), a final point addition (R = P1 + P2,
where P1/P2 are the two ladders' final points), and the final reduction
v = R.x mod n, compared against the signature's r. All arithmetic is mod the
field prime p (point coordinates) or the subgroup order n (header scalars).

This transcript is either GENUINE (every value is exactly what the algorithm
would produce) or exactly ONE printed value on ONE line was corrupted by a
single bit flip, with everything after it recomputed consistently from the
corrupted value. You do not know which section, which op, or which line.

How to check (follow these rules exactly):

1. LOCAL CHECK. Every printed [addition]/[multiplication]/[reduction] value is
   checkable from values printed on earlier lines alone (the op's own x1/y1[
   /x2/y2] seed -- x1/y1 come from the previous op's printed x3/y3 within the
   same ladder, or, for ladder 2's very first op and the final point addition,
   from the header/ladder outputs -- plus any earlier line within the SAME
   op). The one [inverse-check] line per op (`inv`, or header's `w`) is
   checkable via its own self-check: inv * denominator mod p == 1 (or, for
   `w`: w * s mod n == 1). NEVER substitute one of your own computed values
   for a printed operand -- always read operands from the transcript.{recheck_reminder}

2. RECHECK BEFORE FLAGGING. If your computed value disagrees with the printed
   value, redo THAT ONE computation two more times, independently. Only a
   mismatch confirmed in at least 2 of 3 independent recomputations may drive
   a TAMPERED verdict.

3. CHECK EVERYTHING. Check the header (w, u1, u2), every op in both ladders
   (doubling ops process one scalar bit each; addition ops appear only where
   the scalar's bit is 1), the final point addition, and the final reduction
   v. The corruption could be anywhere.

4. OUTPUT CONTRACT. Do ALL arithmetic in your private reasoning. Your VISIBLE
   response must be ONLY: first the single JSON object described below, then
   the fixed final answer block, and nothing else. Do NOT write op-by-op prose
   in the visible output.

JSON object (emit exactly one, before the final block; compact keys as shown):
{
  "call": "GENUINE" or "TAMPERED",
  "tamper_section": "<one of header, ladder1, ladder2, final_add, v, or null>",
  "tamper_op_idx": <0-based index of the op WITHIN that section's op list (0
    for header/final_add/v, which have no numbered op list) or null>,
  "tamper_step": "<the exact field name as printed on that line, e.g. y3, lam,
    u1_raw, inv, or null>",
  "p_tampered": <float 0.00 to 1.00>,
  "overall_note": "<one line>"
}

Final answer block (exactly these six lines, last thing in your response):

VERDICT: GENUINE or TAMPERED
SECTION: <header, ladder1, ladder2, final_add, v, or NONE>
OP_IDX: <op index as printed, or NONE>
STEP: <field name as printed, or NONE>
P_TAMPERED: <your probability from 0.00 to 1.00 that this transcript is tampered>
REASONING: <one line: what you found, citing line numbers>

Transcript:
{trace}
```
