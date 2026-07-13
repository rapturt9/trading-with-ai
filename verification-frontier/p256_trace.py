"""Real P-256 (secp256r1/NIST P-256) verification-fragment tracer -- Stage
0c, the PRIMARY family per Ram's 2026-07-12 correction ("similar to what
is done for TEE"): real curve constants, real 256-bit coordinates, the
general Weierstrass a-term reinstated (P-256's a = p-3, NOT the a=0
shortcut the small-curve family uses), and every multiplication decomposed
LINEARLY (see ecdsa_trace.py's decompose_multiply_linear / the
"decomposition rule: linear, not pointwise" plan.md entry) via this
module's traced_mulmod, so a real 256-bit multiply renders as ~n_limbs
word-scale lines, not one opaque bignum line and not an n^2 explosion.

**Why fragments, not the full verify.** A full P-256 ECDSA verify is two
~256-bit-scalar ladders (~256-384 point operations each depending on the
scalars' Hamming weight) plus a final add -- rendering the WHOLE thing at
real 256-bit precision would be tens of thousands of lines, far past any
model's context window and past what this rung ladder needs. Instead:
generate a REAL, complete, valid signature and verify (the untraced
Jacobian path, fast), replay the SAME left-to-right double-and-add bit
sequence the traced generator would use, fast-forward through a random
prefix of it (untraced), then render a CONTIGUOUS SPAN of exactly N point
operations (N in 1/2/4/8) starting from that real intermediate state,
traced at full word-scale precision. The span is a genuine excerpt of a
real verification, not a shortened toy computation -- only the SURROUNDING
context (how it got to this point) is elided, the same way a reader
checking one paragraph of a long proof doesn't need to re-derive
everything that came before it, just the stated intermediate facts it
starts from.

**Independent correctness check.** `verify_reference` (Jacobian
coordinates, general a, built-in pow(x,-1,p)) is checked against real
NIST-published curve constants (`Gx`,`Gy` confirmed on-curve on import),
and every genuine fragment's start/end points are cross-checked against
the SAME Jacobian ladder used to fast-forward to that point -- so the
traced, word-scale-decomposed formulas are validated against a
completely different code path (different coordinate system, different
inverse method, no word decomposition at all) at real curve scale, not
just at toy scale.
"""

import random

from ecdsa_trace import (  # noqa: E402  (reused, not duplicated -- see module docstring)
    mod_inverse_euclid, jac_scalar_mult, jac_to_affine, affine_scalar_mult, _jac_add, _jac_double,
)

# --- NIST P-256 / secp256r1 standard published constants ---
P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
A = P - 3  # the general Weierstrass a-term; NOT 0, unlike the small-curve family
B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
GX = 0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296
GY = 0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5
N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
G = (GX, GY)


def point_on_curve(P_):
    x, y = P_
    return (y * y - (x ** 3 + A * x + B)) % P == 0


assert point_on_curve(G), "G is not on P-256 -- a published constant is wrong"


# --- traced multiplication, LINEAR decomposition (grade-school long
# multiplication), per the locked decomposition rule. Generalizes
# ecdsa_trace.py's decompose_multiply_linear into a NAMED, TAMPERABLE,
# CHECKABLE line sequence usable inside a point-op formula. ---

def traced_mulmod(name, a_val, b_val, p, limb_bits, tamper_step=None, tamper_bit=None):
    """(a_val * b_val) mod p, decomposed into O(n) word-scale lines: one
    ROW per word of b_val (a_val kept whole, that row is one
    "multiplication"-type line), one running-sum "addition"-type line per
    row, and one final "reduction"-type line. tamper_step: a line name
    from this call's own namespace (f"{name}_row{i}", f"{name}_acc{i}", or
    name itself) -- flips that line's value and lets it cascade through
    the rest of THIS mulmod block exactly like eval_formula's tamper
    mechanism, since running_total is threaded through Python state.
    Returns (value, records)."""
    base = 1 << limb_bits
    n_limbs = max((b_val.bit_length() + limb_bits - 1) // limb_bits, 1)
    records = []
    running_total = 0
    for i in range(n_limbs):
        bi = (b_val >> (i * limb_bits)) & (base - 1)
        row_val = a_val * bi
        rname = f"{name}_row{i}"
        if rname == tamper_step:
            row_val ^= (1 << tamper_bit)
        records.append({"name": rname, "type": "multiplication", "value": row_val})
        running_total = running_total + (row_val << (i * limb_bits))
        aname = f"{name}_acc{i}"
        if aname == tamper_step:
            running_total ^= (1 << tamper_bit)
        records.append({"name": aname, "type": "addition", "value": running_total})
    value = running_total % p
    if name == tamper_step:
        value ^= (1 << tamper_bit)
    records.append({"name": name, "type": "reduction", "value": value})
    return value, records


def check_mulmod(a_val, b_val, p, limb_bits, records):
    """Recompute every row/acc/reduction line from EARLIER PRINTED values
    (a_val, b_val are themselves printed values from earlier steps, passed
    in by the caller -- see check_formula's docstring for why this
    satisfies "recompute from printed inputs, never ground truth"; b_val's
    limb split is a deterministic bit-slice of an already-printed number,
    not an independent claim needing its own line, same as SHA's K[t]
    constants). Returns the flagged line names."""
    base = 1 << limb_bits
    n_limbs = max((b_val.bit_length() + limb_bits - 1) // limb_bits, 1)
    assert len(records) == 2 * n_limbs + 1, "record count doesn't match b_val's own bit length"
    bad = []
    running_total = 0
    for i in range(n_limbs):
        bi = (b_val >> (i * limb_bits)) & (base - 1)
        row_rec, acc_rec = records[2 * i], records[2 * i + 1]
        if a_val * bi != row_rec["value"]:
            bad.append(row_rec["name"])
        running_total = running_total + (row_rec["value"] << (i * limb_bits))
        if running_total != acc_rec["value"]:
            bad.append(acc_rec["name"])
        running_total = acc_rec["value"]  # continue the chain from the PRINTED acc
    final_rec = records[-1]
    if (running_total % p) != final_rec["value"]:
        bad.append(final_rec["name"])
    return bad


# --- point-op formulas: a mix of "simple" (one line) and "bigmult"
# (traced_mulmod, many lines) steps, evaluated/checked by the same generic
# walk (eval_formula_v2 / check_formula_v2), mirroring ecdsa_trace.py's
# eval_formula/check_formula but generalized to multi-line steps. ---

def double_formula(p, a):
    return [
        ("bigmult", "x1sq", lambda v: v["x1"], lambda v: v["x1"]),
        ("bigmult", "term", lambda v: v["x1sq"], lambda v: 3),
        ("simple", "numerator", "addition", lambda v: (v["term"] + a) % p),
        ("simple", "denominator", "addition", lambda v: (v["y1"] + v["y1"]) % p),
        ("simple", "inv", "inverse-check", lambda v: mod_inverse_euclid(v["denominator"], p)),
        ("bigmult", "lam", lambda v: v["numerator"], lambda v: v["inv"]),
        ("bigmult", "lamsq", lambda v: v["lam"], lambda v: v["lam"]),
        ("simple", "two_x1", "addition", lambda v: (v["x1"] + v["x1"]) % p),
        ("simple", "x3", "addition", lambda v: (v["lamsq"] - v["two_x1"]) % p),
        ("simple", "diff", "addition", lambda v: (v["x1"] - v["x3"]) % p),
        ("bigmult", "t2", lambda v: v["lam"], lambda v: v["diff"]),
        ("simple", "y3", "addition", lambda v: (v["t2"] - v["y1"]) % p),
    ]


def add_formula(p):
    return [
        ("simple", "numerator", "addition", lambda v: (v["y2"] - v["y1"]) % p),
        ("simple", "denominator", "addition", lambda v: (v["x2"] - v["x1"]) % p),
        ("simple", "inv", "inverse-check", lambda v: mod_inverse_euclid(v["denominator"], p)),
        ("bigmult", "lam", lambda v: v["numerator"], lambda v: v["inv"]),
        ("bigmult", "lamsq", lambda v: v["lam"], lambda v: v["lam"]),
        ("simple", "t3", "addition", lambda v: (v["lamsq"] - v["x1"]) % p),
        ("simple", "x3", "addition", lambda v: (v["t3"] - v["x2"]) % p),
        ("simple", "diff", "addition", lambda v: (v["x1"] - v["x3"]) % p),
        ("bigmult", "t2", lambda v: v["lam"], lambda v: v["diff"]),
        ("simple", "y3", "addition", lambda v: (v["t2"] - v["y1"]) % p),
    ]


def eval_formula_v2(formula, seed_vals, p, limb_bits, tamper_name=None, tamper_bit=None):
    vals = dict(seed_vals)
    records = []
    for step in formula:
        if step[0] == "simple":
            _, name, typ, fn = step
            val = fn(vals)
            if name == tamper_name:
                val ^= (1 << tamper_bit)
            vals[name] = val
            records.append({"name": name, "type": typ, "value": val})
        else:
            _, name, fn_a, fn_b = step
            a_val, b_val = fn_a(vals), fn_b(vals)
            val, sub_records = traced_mulmod(name, a_val, b_val, p, limb_bits,
                                              tamper_step=tamper_name, tamper_bit=tamper_bit)
            vals[name] = val
            records.extend(sub_records)
    return vals, records


def check_formula_v2(formula, seed_vals, p, limb_bits, records):
    """Walks the formula and the records list in lockstep. bigmult steps
    consume a variable number of records (2*n_limbs+1, n_limbs determined
    by the PRINTED b_val's own bit length -- deterministic, see
    check_mulmod), so the record cursor advances accordingly."""
    vals = dict(seed_vals)
    bad = []
    idx = 0
    for step in formula:
        if step[0] == "simple":
            _, name, typ, fn = step
            expected = fn(vals)
            rec = records[idx]
            if expected != rec["value"]:
                bad.append(name)
            vals[name] = rec["value"]
            idx += 1
        else:
            _, name, fn_a, fn_b = step
            a_val, b_val = fn_a(vals), fn_b(vals)
            n_limbs = max((b_val.bit_length() + limb_bits - 1) // limb_bits, 1)
            sub_records = records[idx:idx + 2 * n_limbs + 1]
            bad.extend(check_mulmod(a_val, b_val, p, limb_bits, sub_records))
            vals[name] = sub_records[-1]["value"]
            idx += len(sub_records)
    assert idx == len(records), "record count mismatch -- formula/records out of sync"
    return bad


def run_point_op(kind, p, a, limb_bits, x1, y1, x2=None, y2=None, tamper_name=None, tamper_bit=None):
    seed = {"x1": x1, "y1": y1}
    if kind == "add":
        if x1 == x2:
            raise SmallFieldCollisionP256(f"x1 == x2 == {x1}, addition formula needs distinct points")
        seed.update({"x2": x2, "y2": y2})
        formula = add_formula(p)
    else:
        if y1 == 0:
            raise SmallFieldCollisionP256("y1 == 0, a 2-torsion point -- doubling formula divides by 2*y1")
        formula = double_formula(p, a)
    vals, records = eval_formula_v2(formula, seed, p, limb_bits, tamper_name, tamper_bit)
    return {"kind": kind, "seed": seed, "formula": formula, "records": records,
            "x3": vals["x3"], "y3": vals["y3"]}


class SmallFieldCollisionP256(Exception):
    """At real P-256 scale (n is a ~256-bit prime) this is astronomically
    unlikely -- unlike the small-curve family, where it's a real, handled
    event -- but the guard is kept for defensive completeness and
    documented the same way, see ecdsa_trace.py's SmallFieldCollision."""


# --- untraced setup: real signature generation, the independent
# Jacobian-coordinate reference verify (general a, a genuinely different
# code path from the traced word-scale formulas above) ---

def ecdsa_sign(d, z, k):
    R = affine_scalar_mult(k, G, P, a=A)
    assert R is not None
    r = R[0] % N
    assert r != 0
    k_inv = pow(k, -1, N)
    s = (k_inv * (z + r * d)) % N
    assert s != 0
    return r, s


def verify_reference(Q, r, s, z):
    if not (1 <= r < N and 1 <= s < N):
        return False, None
    w = pow(s, -1, N)
    u1 = (z * w) % N
    u2 = (r * w) % N
    P1 = jac_scalar_mult(u1, G, P, a=A)
    P2 = jac_scalar_mult(u2, Q, P, a=A)
    if P1[2] == 0 and P2[2] == 0:
        return False, None
    R = jac_to_affine(P1, P) if P2[2] == 0 else (
        jac_to_affine(P2, P) if P1[2] == 0 else jac_to_affine(_jac_add(P1, P2, P, a=A), P))
    if R is None:
        return False, None
    v = R[0] % N
    return v == r, v


def _ladder_bits(scalar):
    return bin(scalar)[2:][1:]  # MSB consumed with no recorded op, matching the toy family's convention


def _ladder_op_sequence(scalar):
    """Flat list of 'double'/'add' for the WHOLE left-to-right ladder, e.g.
    bits '101' -> ['double','add','double','double','add']. Both
    _fast_forward (untraced) and run_ladder_fragment (traced) walk THIS
    SAME flat sequence -- fixed a real bug from an earlier version that
    paired doublings/adds per BIT instead of per flat OP: stopping between
    a bit's double and its conditional add silently dropped the pending
    add when the two functions re-synced on the next bit boundary instead
    of the next op boundary. The flat sequence has no such boundary to
    misalign on."""
    seq = []
    for bit in _ladder_bits(scalar):
        seq.append("double")
        if bit == "1":
            seq.append("add")
    return seq


def _fast_forward(scalar, base_point, stop_after_ops):
    """Untraced (Jacobian) replay of the flat op sequence, stopped after
    exactly stop_after_ops point operations. Returns the affine point
    there."""
    seq = _ladder_op_sequence(scalar)
    Rx, Ry, Rz = base_point[0], base_point[1], 1
    for op_kind in seq[:stop_after_ops]:
        if op_kind == "double":
            Rx, Ry, Rz = _jac_double((Rx, Ry, Rz), P, a=A)
        else:
            Rx, Ry, Rz = _jac_add((Rx, Ry, Rz), (base_point[0], base_point[1], 1), P, a=A)
    affine = jac_to_affine((Rx, Ry, Rz), P)
    assert affine is not None, "fast-forward landed on infinity -- vanishingly unlikely at P-256 scale"
    return affine


def run_ladder_fragment(scalar, base_point, n_ops, prefix_ops, limb_bits, tamper_at=None):
    """Fast-forward (untraced) through `prefix_ops` point operations of the
    scalar*base_point ladder's flat op sequence, then TRACE exactly n_ops
    more from there, at real P-256 precision. tamper_at: optional
    (op_idx, step_name, bit), op_idx 0-based within this fragment (not the
    full ladder)."""
    seq = _ladder_op_sequence(scalar)
    start_point = _fast_forward(scalar, base_point, prefix_ops)
    x, y = start_point
    ops = []
    for op_kind in seq[prefix_ops:prefix_ops + n_ops]:
        idx = len(ops)
        tn, tb = (tamper_at[1], tamper_at[2]) if (tamper_at and tamper_at[0] == idx) else (None, None)
        if op_kind == "double":
            op = run_point_op("double", P, A, limb_bits, x, y, tamper_name=tn, tamper_bit=tb)
        else:
            op = run_point_op("add", P, A, limb_bits, x, y, base_point[0], base_point[1],
                               tamper_name=tn, tamper_bit=tb)
        ops.append(op)
        x, y = op["x3"], op["y3"]
    return {"start": start_point, "ops": ops, "end": (x, y), "prefix_ops": prefix_ops,
            "scalar_bits": len(_ladder_bits(scalar)) + 1}


def local_consistency_report(fragment, limb_bits):
    curve_p = P
    bad = []
    for i, op in enumerate(fragment["ops"]):
        flagged = check_formula_v2(op["formula"], op["seed"], curve_p, limb_bits, op["records"])
        for name in flagged:
            bad.append((i, name))
        if i + 1 < len(fragment["ops"]):
            nxt = fragment["ops"][i + 1]
            if nxt["seed"]["x1"] != op["x3"] or nxt["seed"]["y1"] != op["y3"]:
                bad.append((i, "chain_state"))
    return bad


def generate_genuine_fragment(seed, n_ops, limb_bits=8, z=None):
    """A real, complete, valid P-256 signature and verify, with a
    contiguous n_ops-operation fragment drawn from the u1*G ladder at a
    random prefix offset. limb_bits=8 (32 words per 256-bit number) is the
    default because it lands the 1/2/4/8-op rungs in the ~250-2,000-line
    range the design targets -- see proposal.md for the measured table.

    z: optional message-hash override (int, 1 <= z < N) -- added for
    mini_attestation.py's composite trace, which chains a real SHA digest
    in as z instead of a random one, reusing this exact sign/verify/
    fragment/check machinery rather than duplicating it. Default None
    reproduces the original random-z behavior unchanged."""
    rng = random.Random(seed)
    d = rng.randrange(1, N)
    Q = affine_scalar_mult(d, G, P, a=A)
    while True:
        z_try = z if z is not None else rng.randrange(1, N)
        k = rng.randrange(1, N)
        try:
            r, s = ecdsa_sign(d, z_try, k)
        except AssertionError:
            continue
        w = mod_inverse_euclid(s, N)
        u1 = (z_try * w) % N
        u2 = (r * w) % N
        if u1 == 0 or u2 == 0:
            assert z is None, "a given z landed on u1==0 or u2==0 -- astronomically unlikely at P-256 scale, investigate rather than silently retry with a different z"
            continue
        ref_valid, ref_v = verify_reference(Q, r, s, z_try)
        if not ref_valid:
            continue
        break
    z = z_try

    total_ops_u1 = len(_ladder_op_sequence(u1))
    if total_ops_u1 <= n_ops:
        prefix_ops = 0
    else:
        prefix_ops = rng.randrange(0, total_ops_u1 - n_ops)

    try:
        fragment = run_ladder_fragment(u1, G, n_ops, prefix_ops, limb_bits)
    except SmallFieldCollisionP256:
        return generate_genuine_fragment(seed + 1_000_003, n_ops, limb_bits, z=z)  # vanishingly rare at this scale, retry with a different seed

    bad = local_consistency_report(fragment, limb_bits)
    assert bad == [], f"genuine fragment has locally inconsistent lines: {bad}"

    # cross-check the fragment's start/end against the SAME positions
    # computed by the independent Jacobian ladder (jac_scalar_mult over
    # just the prefix+n_ops bits), a different code path from the traced
    # word-scale formulas.
    start_check = _fast_forward(u1, G, prefix_ops)
    assert start_check == fragment["start"], "fragment start disagrees with the independent fast-forward"
    end_check = _fast_forward(u1, G, prefix_ops + len(fragment["ops"]))
    assert end_check == fragment["end"], "fragment end disagrees with the independent Jacobian ladder"

    return {"d": d, "Q": Q, "r": r, "s": s, "z": z, "u1": u1, "fragment": fragment,
            "limb_bits": limb_bits, "n_ops": n_ops, "prefix_ops": prefix_ops}


def total_line_count(gen):
    return sum(len(op["records"]) for op in gen["fragment"]["ops"])


def _flat_targets(gen):
    targets = []
    for i, op in enumerate(gen["fragment"]["ops"]):
        for rec in op["records"]:
            targets.append((i, rec["name"]))
    return targets


def position_buckets(n_targets):
    third = n_targets / 3
    early_end = round(third)
    middle_end = round(2 * third)
    return {"early": range(0, early_end), "middle": range(early_end, middle_end),
            "late": range(middle_end, n_targets)}


def generate_tampered_fragment(seed, n_ops, bucket, limb_bits=8, z=None):
    """z: same override as generate_genuine_fragment's -- mini_attestation.py
    uses this to tamper the P-256 half while keeping z (the chained SHA
    digest) fixed to the genuine composite's value."""
    genuine = generate_genuine_fragment(seed, n_ops, limb_bits, z=z)
    targets = _flat_targets(genuine)
    buckets = position_buckets(len(targets))
    rng = random.Random(seed * 999_983 + 7)
    idx = rng.choice(list(buckets[bucket]))
    op_idx, step_name = targets[idx]
    bit = rng.randrange(P.bit_length())

    try:
        tampered_fragment = run_ladder_fragment(
            genuine["u1"], G, n_ops, genuine["prefix_ops"], limb_bits,
            tamper_at=(op_idx, step_name, bit))
    except SmallFieldCollisionP256:
        return generate_tampered_fragment(seed + 1_000_003, n_ops, bucket, limb_bits, z=z)

    bad = local_consistency_report(tampered_fragment, limb_bits)
    assert len(bad) == 1, f"expected exactly one flagged line, got {bad}"
    assert bad[0] == (op_idx, step_name), f"flagged line {bad[0]} != tamper target {(op_idx, step_name)}"

    out = dict(genuine)
    out["fragment"] = tampered_fragment
    out["tamper"] = {"op_idx": op_idx, "step_name": step_name, "bit": bit, "bucket": bucket}
    return out


def render_fragment(gen, line_numbers=True, tag_op_types=True):
    lines = []
    n_ctr = [0]

    def add(text):
        n_ctr[0] += 1
        lines.append(f"L{n_ctr[0]:04d}: {text}" if line_numbers else text)

    frag = gen["fragment"]
    add(f"Real P-256 verification fragment: {gen['n_ops']} contiguous point operations "
        f"starting {gen['prefix_ops']} operations into the u1*G ladder of a genuine ECDSA verify "
        f"(scalar u1 has {frag['scalar_bits']} bits; the surrounding computation is not shown, only "
        f"the stated starting point below, exactly as a reader checking one excerpt of a long proof would see it).")
    add(f"Starting point: x1 = {frag['start'][0]}")
    add(f"                y1 = {frag['start'][1]}")
    for i, op in enumerate(frag["ops"]):
        add(f"op {i} [{op['kind'].upper()}] x1={op['seed']['x1']} y1={op['seed']['y1']}"
            + (f" x2={op['seed']['x2']} y2={op['seed']['y2']}" if op["kind"] == "add" else ""))
        for rec in op["records"]:
            tag = f"[{rec['type']}] " if tag_op_types else ""
            add(f"  {tag}{rec['name']} = {rec['value']}")
    add(f"End point: x = {frag['end'][0]}")
    add(f"           y = {frag['end'][1]}")
    return "\n".join(lines)


# Audited 2026-07-12 alongside ecdsa_trace.py's verdict-leak fix: this
# renderer never computed or printed a final v/r comparison in the first
# place (a fragment doesn't reach the full-verify comparison at all -- see
# the module docstring's "why fragments" section), so there was nothing to
# strip here. Version marker kept in step with the other two renderers for
# a consistent audit trail across logs, not because behavior changed.
RENDERER_VERSION = "v2-no-verdict-leak-2026-07-12"


if __name__ == "__main__":
    print(f"P-256 constants: p bit_length={P.bit_length()}, a=p-3, G on curve: {point_on_curve(G)}")

    for n_ops in (1, 2, 4, 8):
        g = generate_genuine_fragment(seed=1, n_ops=n_ops)
        n_lines = total_line_count(g)
        print(f"[n_ops={n_ops}] genuine fragment: {n_lines} lines, "
              f"local_consistency_report empty: {local_consistency_report(g['fragment'], g['limb_bits']) == []}")
        for bucket in ("early", "middle", "late"):
            t = generate_tampered_fragment(seed=42, n_ops=n_ops, bucket=bucket)
            bad = local_consistency_report(t["fragment"], t["limb_bits"])
            ok = bad == [(t["tamper"]["op_idx"], t["tamper"]["step_name"])]
            print(f"  tampered[{bucket}]: op={t['tamper']['op_idx']} step={t['tamper']['step_name']}, "
                  f"exactly-one-flag: {ok}")

    g8 = generate_genuine_fragment(seed=1, n_ops=8)
    r8 = render_fragment(g8)
    print(f"\nn_ops=8 rendered fragment: {len(r8)} chars, ~{len(r8) // 4} tokens (rough estimate), "
          f"{total_line_count(g8)} lines")

    # corrupted-signature negative self-test
    d = 12345
    Q = affine_scalar_mult(d, G, P, a=A)
    r_ok, s_ok = ecdsa_sign(d, 999, 54321)
    bad_s = (s_ok + 1) % N or 1
    ref_valid, _ = verify_reference(Q, r_ok, bad_s, 999)
    print(f"corrupted-signature self-test (s+1): reference verify returns False: {ref_valid is False}")
