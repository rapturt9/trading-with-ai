"""Tamper-class stratification for the SHA family: extends
sha256_multiblock.py's single-class (new_a-only) tamper injector to the
five operation-type classes from plan.md's B-design refinement --
"stratify which value gets the bit flip across operation-type outputs (a
bitwise result, an addition result, a message-schedule word, ...) crossed
with position buckets."

Classes covered here (mapped onto SHA's round structure):
  "addition"       -- the original mechanism: flip new_a (the round's final
                       addition output). Delegates straight to
                       sha256_multiblock.generate_tampered.
  "bitwise"         -- flip one of S1/ch/S0/maj (the round's bitwise-op
                       outputs), then recompute every field within that
                       round that depends on it, then resume compression
                       for the rest of the block/message via compress()'s
                       start_round + init_state (no duplicated round loop).
  "schedule_word"   -- corrupt the round's RECORDED copy of W[t] only (the
                       message-schedule word at its point of use), leaving
                       the round's actual temp1/new_a/new_e as originally
                       computed from the TRUE W[t]. This models "the trace
                       shows an inconsistent copy of the schedule word,"
                       checkable by recomputing temp1 from the round's own
                       printed step3+W and finding it doesn't match the
                       printed temp1 -- a pure post-hoc field edit, zero
                       cascade needed since nothing downstream reads the
                       dict's stored W, only step3+W[t] which is baked into
                       the already-computed temp1.

Point-coordinate and inverse-check classes for the ECDSA family live in
ecdsa_trace.py directly (generate_tampered's tamper_class param); this
module is SHA-specific because SHA's round structure (bitwise vs additive
sub-steps within one round) is what the classes are named after.
"""

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sha256_trace import K, MASK32  # noqa: E402

from sha256_multiblock import (  # noqa: E402
    generate_tampered as generate_tampered_addition,
    generate_genuine, global_position_buckets, _blocks, _compress_chain,
    pad_multi_block, hash_hex,
)

sys.path.insert(0, os.path.dirname(__file__))
import sha256_trace as _parent  # noqa: E402  (re-import for compress with start_round)
compress = _parent.compress


BITWISE_FIELDS = ("S1", "ch", "S0", "maj")


def _recompute_bitwise_cascade(r, field, bit):
    """Given round dict r (as produced by compress()) and a bitwise field
    to flip, recompute every field within THIS round that depends on it,
    using the same formulas as sha256_trace.local_consistency_report's
    checks (the generation-side mirror of that checking logic). Returns a
    new round dict and the (a,b,c,d,e,f,g,h) state to feed the next round.
    """
    tampered = dict(r)
    tampered[field] = r[field] ^ (1 << bit)

    S1 = tampered["S1"]
    ch = tampered["ch"]
    S0 = tampered["S0"]
    maj = tampered["maj"]
    step1 = (r["h_in"] + S1) & MASK32
    step2 = (step1 + ch) & MASK32
    step3 = (step2 + r["K"]) & MASK32
    temp1 = (step3 + r["W"]) & MASK32
    temp2 = (S0 + maj) & MASK32
    new_a = (temp1 + temp2) & MASK32
    new_e = (r["d_in"] + temp1) & MASK32

    tampered.update({"step1": step1, "step2": step2, "step3": step3, "temp1": temp1,
                      "temp2": temp2, "a": new_a, "b": r["a_in"], "c": r["b_in"], "d": r["c_in"],
                      "e": new_e, "f": r["e_in"], "g": r["f_in"], "h": r["g_in"]})
    next_state = (new_a, r["a_in"], r["b_in"], r["c_in"], new_e, r["e_in"], r["f_in"], r["g_in"])
    return tampered, next_state


def _cascade_block(genuine_rounds, W, tamper_round, field, bit):
    """Splice a within-round tamper into a genuine block's round list and
    resume compression for the remaining rounds via compress()'s
    start_round + init_state (no duplicated loop). Returns the full
    (tampered) round list and the block's final state."""
    r = genuine_rounds[tamper_round]
    tampered_round, next_state = _recompute_bitwise_cascade(r, field, bit)
    remaining = 64 - (tamper_round + 1)
    if remaining == 0:
        return genuine_rounds[:tamper_round] + [tampered_round], list(next_state)
    later_rounds, final = compress(W, n_rounds=remaining, init_state=next_state, start_round=tamper_round + 1)
    return genuine_rounds[:tamper_round] + [tampered_round] + later_rounds, final


def generate_tampered_bitwise(seed, bucket, n_blocks):
    """tamper_class == 'bitwise': flip one of S1/ch/S0/maj in a chosen
    round, cascade through the rest of that block and every later block."""
    rng = random.Random(seed)
    msg_len = n_blocks * 64 - 9
    msg = bytes(rng.randrange(32, 127) for _ in range(msg_len))
    padded = pad_multi_block(msg, n_blocks)
    blocks = _blocks(padded)

    buckets = global_position_buckets(n_blocks)
    global_step = rng.choice(list(buckets[bucket]))
    tamper_block, tamper_round = divmod(global_step, 64)
    field = rng.choice(BITWISE_FIELDS)
    bit = rng.randrange(32)

    genuine_traces, genuine_final = _compress_chain(blocks)
    tampered_block_traces = []
    state = None
    for bi, block in enumerate(blocks):
        if bi < tamper_block:
            tampered_block_traces.append(genuine_traces[bi])
        elif bi == tamper_block:
            W = genuine_traces[bi]["W"]
            rounds, final = _cascade_block(genuine_traces[bi]["rounds"], W, tamper_round, field, bit)
            tampered_block_traces.append({"W": W, "rounds": rounds, "final": final})
        else:
            from sha256_trace import compute_message_schedule
            W = compute_message_schedule(block)
            init = tampered_block_traces[bi - 1]["final"]
            rounds, final = compress(W, n_rounds=64, init_state=init)
            tampered_block_traces.append({"W": W, "rounds": rounds, "final": final})

    tampered_final = tampered_block_traces[-1]["final"]
    tampered_digest = hash_hex(tampered_final)
    genuine_digest = hash_hex(genuine_final)
    assert tampered_digest != genuine_digest, "bitwise tamper did not propagate to final digest"

    return {"message": msg, "n_blocks": n_blocks, "block_traces": tampered_block_traces,
            "final": tampered_final, "digest": tampered_digest, "tamper_block": tamper_block,
            "tamper_step": tamper_round, "tamper_field": field, "tamper_bit": bit,
            "bucket": bucket, "global_step": global_step, "tamper_class": "bitwise"}


def generate_tampered_schedule_word(seed, bucket, n_blocks):
    """tamper_class == 'schedule_word': corrupt the round's recorded copy
    of W[t] only (post-hoc field edit, no cascade -- see module docstring).
    """
    rng = random.Random(seed)
    msg_len = n_blocks * 64 - 9
    msg = bytes(rng.randrange(32, 127) for _ in range(msg_len))
    padded = pad_multi_block(msg, n_blocks)
    blocks = _blocks(padded)

    buckets = global_position_buckets(n_blocks)
    global_step = rng.choice(list(buckets[bucket]))
    tamper_block, tamper_round = divmod(global_step, 64)
    bit = rng.randrange(32)

    genuine_traces, genuine_final = _compress_chain(blocks)
    tampered_block_traces = [dict(bt) for bt in genuine_traces]
    tampered_block_traces[tamper_block] = dict(genuine_traces[tamper_block])
    tampered_block_traces[tamper_block]["rounds"] = list(genuine_traces[tamper_block]["rounds"])
    r = dict(tampered_block_traces[tamper_block]["rounds"][tamper_round])
    r["W"] = r["W"] ^ (1 << bit)
    tampered_block_traces[tamper_block]["rounds"][tamper_round] = r
    # final digest is UNCHANGED (this is a display-only corruption of the
    # recorded field; the round's actual temp1/new_a were already computed
    # from the true W before this edit) -- the tamper is purely local.
    genuine_digest = hash_hex(genuine_final)

    return {"message": msg, "n_blocks": n_blocks, "block_traces": tampered_block_traces,
            "final": genuine_traces[-1]["final"], "digest": genuine_digest, "tamper_block": tamper_block,
            "tamper_step": tamper_round, "tamper_field": "W", "tamper_bit": bit,
            "bucket": bucket, "global_step": global_step, "tamper_class": "schedule_word"}


def local_consistency_report(trace):
    """Same invariant checker as sha256_multiblock's, reused unmodified via
    import to avoid duplicating the per-round arithmetic checks."""
    from sha256_multiblock import local_consistency_report as _check
    return _check(trace)


if __name__ == "__main__":
    from sha256_multiblock import local_consistency_report as check

    for n_blocks in (1, 2):
        for bucket in ("early", "middle", "late"):
            t = generate_tampered_bitwise(seed=7, bucket=bucket, n_blocks=n_blocks)
            bad = check(t)
            expected_fields = {"step1", "step2", "step3", "temp1", "temp2", "new_a", "S1", "ch", "S0", "maj"}
            # the flagged field is whichever of the checks dict's keys first
            # diverges from the recompute; for a bitwise flip that's the
            # flipped field itself (S1/ch/S0/maj aren't in checks' key set,
            # so the first DOWNSTREAM addition it feeds is what's flagged --
            # see local_consistency_report: it only checks step1..new_e/new_a).
            ok = len(bad) == 1 and bad[0][0] == t["tamper_block"] and bad[0][1] == t["tamper_step"]
            print(f"[n_blocks={n_blocks}/{bucket}/bitwise] field={t['tamper_field']} "
                  f"block={t['tamper_block']} round={t['tamper_step']}, "
                  f"digest changed: {True}, exactly one flag at tamper site: {ok}, flags={bad}")

            t2 = generate_tampered_schedule_word(seed=7, bucket=bucket, n_blocks=n_blocks)
            bad2 = check(t2)
            ok2 = bad2 == [(t2["tamper_block"], t2["tamper_step"], "temp1")]
            print(f"[n_blocks={n_blocks}/{bucket}/schedule_word] "
                  f"block={t2['tamper_block']} round={t2['tamper_step']}, "
                  f"local_consistency_report == expected [temp1]: {ok2}, flags={bad2}")
