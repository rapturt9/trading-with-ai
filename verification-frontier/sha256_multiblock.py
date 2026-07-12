"""Multi-block SHA-256 trace generator: the length-scaling axis of the N50
ops-horizon design (verification-frontier proposal.md, workstream B).

Imports and extends ../sha256_trace.py rather than
duplicating it: reuses K, H0, MASK32, rotr, compute_message_schedule,
compress (now accepting an init_state kwarg, see that file), render_dual
(now accepting a binary_state kwarg), position_buckets, hash_hex, and the
internal _Liner/_fmt_word helpers. The only genuinely new logic here is
Merkle-Damgard chaining across blocks (feeding one block's `final` in as
the next block's `init_state`) and a global (cross-block) position axis
for tamper placement.

Rung sizes: n_blocks in {1, 2, 4, 8, ...}, each block = 64 rounds = 448
tracked arithmetic operations (matches rq3-replication's "448 such
additions per trace" for n_blocks=1), so n_blocks=8 is a ~3,584-operation
trace, per structure.md's "SHA at 1/2/4/8 blocks (448 to 3,584 additions)".

Message length is chosen as exactly n_blocks*64 - 9 bytes so standard
SHA-256 padding (0x80 + zero-pad + 8-byte bit-length) fills to precisely
n_blocks blocks with zero padding bytes wasted or spilled into an extra
block -- every rung has an exact, predictable operation count.
"""

import hashlib
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sha256_trace import (  # noqa: E402
    K, H0, MASK32, rotr, compute_message_schedule, compress, render_dual,
    position_buckets, hash_hex, _fmt_word, _fmt_dec, _Liner,
)


def pad_multi_block(msg_bytes, n_blocks):
    """Pad msg_bytes into exactly n_blocks 64-byte blocks. Requires
    len(msg_bytes) == n_blocks*64 - 9 (see module docstring)."""
    expected_len = n_blocks * 64 - 9
    assert len(msg_bytes) == expected_len, (
        f"message must be exactly {expected_len} bytes for n_blocks={n_blocks} "
        f"(got {len(msg_bytes)})"
    )
    bit_len = len(msg_bytes) * 8
    padded = msg_bytes + b"\x80" + bit_len.to_bytes(8, "big")
    assert len(padded) == n_blocks * 64
    return padded


def _blocks(padded):
    return [padded[i * 64:(i + 1) * 64] for i in range(len(padded) // 64)]


def _compress_chain(blocks, tamper_block=None, tamper_step=None, tamper_bit=None):
    """Run compress() over every 64-byte block, chaining final -> init_state.
    If tamper_block/tamper_step/tamper_bit are set, that one round's `new_a`
    is flipped and every block from tamper_block onward is recomputed from
    the tampered state (Merkle-Damgard chaining does this automatically:
    a tampered `final` just becomes the next block's `init_state`).

    Returns (block_traces, final) where block_traces is a list of dicts
    {"W": ..., "rounds": ..., "final": ...} and final is the last block's
    final state (the digest words).
    """
    state = H0
    block_traces = []
    for bi, block in enumerate(blocks):
        W = compute_message_schedule(block)
        ts = tamper_step if (tamper_block is not None and bi == tamper_block) else None
        rounds, final = compress(W, tamper_step=ts, tamper_bit=tamper_bit, init_state=state)
        block_traces.append({"W": W, "rounds": rounds, "final": final})
        state = final
    return block_traces, state


def generate_genuine(seed, n_blocks, message=None):
    """message: optional pre-built bytes override, exactly n_blocks*64-9
    long (see pad_multi_block). Added for report_payload.py's report-
    shaped payloads, so they reuse this exact generator/chain/tamper/
    render/check machinery instead of duplicating it -- default None
    reproduces the original random-message behavior unchanged."""
    rng = random.Random(seed)
    msg_len = n_blocks * 64 - 9
    msg = message if message is not None else bytes(rng.randrange(32, 127) for _ in range(msg_len))
    padded = pad_multi_block(msg, n_blocks)
    blocks = _blocks(padded)
    block_traces, final = _compress_chain(blocks)
    digest = hash_hex(final)
    assert digest == hashlib.sha256(msg).hexdigest(), (
        "multi-block trace generator disagrees with hashlib"
    )
    return {"message": msg, "n_blocks": n_blocks, "block_traces": block_traces,
            "final": final, "digest": digest}


def global_position_buckets(n_blocks):
    """early/middle/late thirds over the full n_blocks*64 round range."""
    return position_buckets(n_blocks * 64)


def generate_tampered(seed, bucket, n_blocks, message=None):
    """message: same override as generate_genuine's."""
    rng = random.Random(seed)
    msg_len = n_blocks * 64 - 9
    msg = message if message is not None else bytes(rng.randrange(32, 127) for _ in range(msg_len))
    padded = pad_multi_block(msg, n_blocks)
    blocks = _blocks(padded)

    total_rounds = n_blocks * 64
    buckets = global_position_buckets(n_blocks)
    global_step = rng.choice(list(buckets[bucket]))
    tamper_block, tamper_step = divmod(global_step, 64)
    tamper_bit = rng.randrange(32)

    genuine_traces, genuine_final = _compress_chain(blocks)
    tampered_traces, tampered_final = _compress_chain(
        blocks, tamper_block=tamper_block, tamper_step=tamper_step, tamper_bit=tamper_bit)

    genuine_digest = hash_hex(genuine_final)
    tampered_digest = hash_hex(tampered_final)
    assert genuine_digest == hashlib.sha256(msg).hexdigest()
    assert tampered_digest != genuine_digest, "tamper did not propagate to final digest"
    # prefix identical through the tamper block (and, within that block, through
    # the tamper round); every later block's rounds must differ since the whole
    # chain re-derives from the tampered running state.
    for bi in range(n_blocks):
        g_rounds = genuine_traces[bi]["rounds"]
        t_rounds = tampered_traces[bi]["rounds"]
        if bi < tamper_block:
            assert g_rounds == t_rounds, f"tamper leaked upstream into block {bi}"
        elif bi == tamper_block:
            assert g_rounds[:tamper_step] == t_rounds[:tamper_step], "tamper leaked upstream in-block"
            assert g_rounds[tamper_step:] != t_rounds[tamper_step:], "tamper did not propagate in-block"
        else:
            assert g_rounds != t_rounds, f"tamper did not propagate to block {bi}"

    return {"message": msg, "n_blocks": n_blocks, "block_traces": tampered_traces,
            "final": tampered_final, "digest": tampered_digest,
            "tamper_block": tamper_block, "tamper_step": tamper_step,
            "tamper_bit": tamper_bit, "bucket": bucket, "global_step": global_step,
            "total_rounds": total_rounds}


def _single_block_trace(trace, block_idx):
    """Adapt one block's {W, rounds, final} into the single-block dict shape
    render_dual expects, so render_dual can be reused per block unmodified."""
    bt = trace["block_traces"][block_idx]
    return {"message": trace["message"], "W": bt["W"], "rounds": bt["rounds"],
            "final": bt["final"], "digest": hash_hex(bt["final"]), "n_rounds": 64}


def render_multiblock(trace, line_numbers=True, binary_bitops=True, binary_new=True,
                       decimal_additions=True, binary_state=True, tag_op_types=False):
    """Render an n_blocks trace by reusing render_dual per block (no
    duplicated round-printing logic): print the message once, then each
    block's schedule+rounds via render_dual with its header/footer lines
    stripped, plus one chaining line per block boundary so the model can
    verify block i+1's initial state equals block i's final state without
    re-deriving it.

    tag_op_types: passed straight through to render_dual (see its
    docstring) -- part of the op-counting convention's per-line type
    tagging, added for the SHA family to match ecdsa_trace.py's renderer.
    """
    L = _Liner(line_numbers)
    n_blocks = trace["n_blocks"]
    L.add(f"Message (hex): {trace['message'].hex()} ({n_blocks} block(s) after padding)")
    for bi in range(n_blocks):
        block_dict = _single_block_trace(trace, bi)
        rendered = render_dual(block_dict, line_numbers=False, binary_bitops=binary_bitops,
                                binary_new=binary_new, decimal_additions=decimal_additions,
                                binary_state=binary_state, tag_op_types=tag_op_types)
        body_lines = rendered.split("\n")[1:-2]  # drop "Message (hex): ..." and blank+digest
        L.add(f"--- Block {bi} of {n_blocks} ---")
        init = H0 if bi == 0 else trace["block_traces"][bi - 1]["final"]
        sw = (lambda x: f"{_fmt_word(x, 'binary')} = {_fmt_dec(x)}") if binary_state else _fmt_dec
        L.add(f"  block {bi} initial state (a..h) = " + ", ".join(sw(w) for w in init) +
              (f"  [chains from block {bi - 1}'s final state]" if bi > 0 else "  [= H0, the fixed SHA-256 IV]"))
        for line in body_lines:
            L.add(line)
        L.add(f"  block {bi} final state (a..h) = " + ", ".join(sw(w) for w in trace["block_traces"][bi]["final"]))
    L.blank()
    L.add(f"Final digest: {trace['digest']}")
    return L.text()


def local_consistency_report(trace):
    """Stage-0 verifier for a multi-block trace: within each block, reuse the
    same per-round arithmetic checks as the parent's local_consistency_report
    (reimplemented here at the block level so the check also covers the
    cross-block chaining invariant); returns a list of (block_idx, round_t,
    field) tuples for every locally inconsistent line. For a genuine trace
    this is empty; for a tampered trace it must be exactly
    [(tamper_block, tamper_step, "new_a")].
    """
    bad = []
    prev_final = H0
    for bi, bt in enumerate(trace["block_traces"]):
        rounds = bt["rounds"]
        # chain check: this block's round-0 inputs must equal the previous
        # block's final state (H0 for block 0).
        r0 = rounds[0]
        in_state = (r0["a_in"], r0["b_in"], r0["c_in"], r0["d_in"],
                    r0["e_in"], r0["f_in"], r0["g_in"], r0["h_in"])
        if tuple(prev_final) != in_state:
            bad.append((bi, 0, "chain_state"))
        prev_round = None
        for r in rounds:
            t = r["t"]
            if prev_round is not None:
                in_state = (r["a_in"], r["b_in"], r["c_in"], r["d_in"],
                            r["e_in"], r["f_in"], r["g_in"], r["h_in"])
                out_state = (prev_round["a"], prev_round["b"], prev_round["c"], prev_round["d"],
                             prev_round["e"], prev_round["f"], prev_round["g"], prev_round["h"])
                if in_state != out_state:
                    bad.append((bi, t, "chain_state"))
            checks = {
                # bitwise outputs, recomputed from the round's own e_in/f_in/g_in
                # and a_in/b_in/c_in -- needed so a "bitwise" tamper class (flip
                # S1/ch/S0/maj directly, see sha256_tamper_classes.py) is actually
                # caught: without these, a self-consistently-cascaded bitwise flip
                # would leave every downstream addition checking out and the
                # invariant (genuine=0, tampered=1) would silently break.
                "S1": rotr(r["e_in"], 6) ^ rotr(r["e_in"], 11) ^ rotr(r["e_in"], 25),
                "ch": (r["e_in"] & r["f_in"]) ^ (~r["e_in"] & r["g_in"]) & MASK32,
                "S0": rotr(r["a_in"], 2) ^ rotr(r["a_in"], 13) ^ rotr(r["a_in"], 22),
                "maj": (r["a_in"] & r["b_in"]) ^ (r["a_in"] & r["c_in"]) ^ (r["b_in"] & r["c_in"]),
                "step1": (r["h_in"] + r["S1"]) & MASK32,
                "step2": (r["step1"] + r["ch"]) & MASK32,
                "step3": (r["step2"] + r["K"]) & MASK32,
                "temp1": (r["step3"] + r["W"]) & MASK32,
                "temp2": (r["S0"] + r["maj"]) & MASK32,
                "new_a": (r["temp1"] + r["temp2"]) & MASK32,
                "new_e": (r["d_in"] + r["temp1"]) & MASK32,
            }
            printed = {"S1": r["S1"], "ch": r["ch"], "S0": r["S0"], "maj": r["maj"],
                       "step1": r["step1"], "step2": r["step2"], "step3": r["step3"],
                       "temp1": r["temp1"], "temp2": r["temp2"], "new_a": r["a"], "new_e": r["e"]}
            for name, computed in checks.items():
                if computed != printed[name]:
                    bad.append((bi, t, name))
            prev_round = r
        prev_final = bt["final"]
    return bad


if __name__ == "__main__":
    for n_blocks in (1, 2, 4, 8):
        g = generate_genuine(seed=1, n_blocks=n_blocks)
        print(f"[n_blocks={n_blocks}] genuine digest matches hashlib: "
              f"{g['digest'] == hashlib.sha256(g['message']).hexdigest()}, "
              f"local_consistency_report empty: {local_consistency_report(g) == []}")
        for bucket in ("early", "middle", "late"):
            t = generate_tampered(seed=42, bucket=bucket, n_blocks=n_blocks)
            bad = local_consistency_report(t)
            expected = [(t["tamper_block"], t["tamper_step"], "new_a")]
            print(f"  [{bucket}] tamper at block {t['tamper_block']} round {t['tamper_step']}, "
                  f"digest changed: {t['digest'] != hashlib.sha256(t['message']).hexdigest()}, "
                  f"local_consistency_report == expected: {bad == expected}")

    g = generate_genuine(seed=1, n_blocks=2)
    rendered = render_multiblock(g)
    print(f"\nn_blocks=2 dual render: {len(rendered)} chars, ~{len(rendered)//4} tokens (rough estimate)")
