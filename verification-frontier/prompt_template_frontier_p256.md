# N50 harness prompt: real P-256 verification-fragment family (PRIMARY)

`{trace}` is substituted with `p256_trace.render_fragment(...)` output. Location
is 2-part -- (op_idx, step) -- not 3-part like the toy-ECDSA family, since a
fragment has no "section" (header/ladder1/ladder2/final_add/v): it's a single
contiguous span drawn from one ladder of a genuine, complete P-256 signature
verify, matching `local_consistency_report`'s own (op_idx, step_name) tuple
format exactly. Uses the fixed (post-verdict-leak-fix) renderer; RENDERER_VERSION
is stored in run metadata, not in the prompt text itself.

```
You are auditing a FRAGMENT of a real P-256 (NIST secp256r1) elliptic-curve
signature-verification computation. Every line is numbered (L0001, L0002,
...) so you can cite an exact line, and every derived value is tagged with
its operation type: [addition], [multiplication], [reduction], or
[inverse-check].

This fragment is a contiguous span of point operations (doublings and
additions) drawn from partway through one scalar-multiplication ladder of a
genuine, complete ECDSA verification -- the surrounding computation (before
the stated starting point, and after the stated end point) is NOT shown to
you, exactly as a reader checking one excerpt of a long proof would see it.
You are given the fragment's starting point (x1, y1) as ground truth; you do
NOT need to verify it, only the operations that follow from it.

This fragment is either GENUINE (every derived value is exactly what the
real P-256 curve arithmetic would produce) or exactly ONE printed value on
ONE line was corrupted by a single bit flip, with everything after it
recomputed consistently from the corrupted value. You do not know which
operation or which line. There is no final verdict rendered anywhere in this
fragment (a fragment stops mid-ladder, before a full verify's final
comparison would even be reached) -- you must find the inconsistency
yourself from the arithmetic, not read it off anywhere.

How to check (follow these rules exactly):

1. LOCAL CHECK. Every printed [addition]/[multiplication]/[reduction] value
   is checkable from values printed on earlier lines alone (the op's own
   x1/y1[/x2/y2] seed -- x1/y1 come from the previous op's printed x3/y3, or
   for the first op, the stated starting point -- plus any earlier line
   within the SAME op). The one [inverse-check] line per op (`inv`) is
   checkable via its own self-check: inv * denominator mod p == 1, where p
   is the real P-256 field prime stated at the top of the fragment. NEVER
   substitute one of your own computed values for a printed operand --
   always read operands from the transcript.

2. RECHECK BEFORE FLAGGING. If your computed value disagrees with the
   printed value, redo THAT ONE computation two more times, independently.
   Only a mismatch confirmed in at least 2 of 3 independent recomputations
   may drive a TAMPERED verdict.

3. CHECK EVERYTHING. Check every op in the fragment, every line within each
   op. The corruption could be anywhere.

4. OUTPUT CONTRACT. Do ALL arithmetic in your private reasoning. Your
   VISIBLE response must be ONLY: first the single JSON object described
   below, then the fixed final answer block, and nothing else. Do NOT write
   op-by-op prose in the visible output.

JSON object (emit exactly one, before the final block; compact keys as shown):
{
  "call": "GENUINE" or "TAMPERED",
  "tamper_op_idx": <0-based index of the op WITHIN this fragment or null>,
  "tamper_step": "<the exact field name as printed on that line, e.g. y3,
    lam, x1sq_raw, inv, or null>",
  "p_tampered": <float 0.00 to 1.00>,
  "overall_note": "<one line>"
}

Final answer block (exactly these five lines, last thing in your response):

VERDICT: GENUINE or TAMPERED
OP_IDX: <op index as printed, or NONE>
STEP: <field name as printed, or NONE>
P_TAMPERED: <your probability from 0.00 to 1.00 that this fragment is tampered>
REASONING: <one line: what you found, citing line numbers>

Transcript:
{trace}
```
