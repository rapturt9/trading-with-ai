"""Small-curve ECDSA verification tracer -- v2 design (Ram's 2026-07-12
correction to the original 256-bit-field-with-shortened-scalars plan).

**What changed and why (design provenance, per Ram):** the v1 design kept
the real 256-bit secp256k1 field but shortened the SCALAR so the ladder
was short. Ram's correction: don't touch the field size down that path at
all -- instead toy-scale the FIELD ITSELF (an 8-bit / 12-bit / 16-bit
prime, not 256-bit), and trace the FULL, real ECDSA VERIFICATION
algorithm end to end (u1/u2 computation, modular inverse, both
double-and-add scalar-mult ladders, point addition, the final
comparison), not just a bare scalar multiplication. No point-granularity
lines: an 8-bit-scale addition is one op, a small multiplication is one
op (rendered as a raw-product line plus a separate reduction line -- see
op-counting convention below), a small modular reduction is one op.
Hash-to-scalar is stubbed: the message hash z is given directly, not
derived via SHA, keeping this family's op count independent of the SHA
family's.

**Op-counting convention (locked by Ram, 2026-07-12), applies to every
line in every trace this module renders:**
  1 op = 1 printed DERIVED value = one checkable line. Inputs and
  constants are not counted. Big operations never count as one op: a
  multiplication decomposes into a raw-product line (type
  "multiplication") and a separate reduction line (type "reduction") --
  this is what keeps small-curve measurements and real 256-bit
  extrapolations in the same unit (a real 256-bit multiply is ~16
  word-scale lines at 32-bit words -- 8 multiplication rows + 8 running-sum
  additions, LINEAR in word count, not the ~64-line pointwise n^2 count an
  earlier version of this decomposition used; see decompose_multiply_linear
  and plan.md's "decomposition rule: linear, not pointwise" entry). Every
  line is tagged with its op type: addition, multiplication, reduction,
  inverse-check (no bitwise type in this family -- the SHA family covers
  that class). Lines are simultaneously the workload, the checkable
  surface, and the tamper-target set.

  The modular-inverse line is printed as ONE checkable claim (the value
  plus its self-check "inv * denominator mod p = 1"), not expanded into
  extended-Euclid's own internal steps. This is deliberate, not a
  shortcut: it is the one line in the whole trace that demonstrates
  verification being cheaper than computation -- checking a claimed
  inverse is one multiplication, computing one from scratch is many.

**Curve construction.** For a chosen field-size in bits: pick the
largest prime p < 2^bits with p = 3 (mod 4) (lets sqrt mod p be computed
directly via pow(x, (p+1)//4, p), no Tonelli-Shanks needed), fix a=0 (as
real secp256k1 does -- this also means the Weierstrass "+a" term is a
real no-op for this curve family and is not rendered as a fake line, see
below), find b by trial so the curve is nonsingular and has a usably
large prime-order subgroup, count the FULL group order by brute force
(Euler's criterion per x-coordinate, O(p) with O(log p) per point -- see
the timing table in proposal.md: 8-bit instant, 16-bit ~0.1s, 20-bit
~1.9s, 24-bit ~36s; this module's routine self-test uses 8/12/16-bit,
all well under a second combined), then find a generator of prime order n
by cofactor clearing.

**Untraced arithmetic (curve construction, signing, the independent
reference check) uses Jacobian coordinates** -- reused from this
project's original ECDSA design, a genuinely different coordinate system
and inverse method (Python's built-in pow(x, -1, p)) from the TRACED,
line-by-line affine arithmetic below, so a bug in one is unlikely to be
mirrored in the other.
"""

import os
import random

MASK32 = 0xFFFFFFFF


# --- primality / curve construction (untraced setup) ---

def is_prime(n):
    if n < 2:
        return False
    if n % 2 == 0:
        return n == 2
    i = 3
    while i * i <= n:
        if n % i == 0:
            return False
        i += 2
    return True


def pick_prime_field(bits):
    """Largest prime p < 2**bits with p = 3 (mod 4)."""
    c = (1 << bits) - 1
    while c % 4 != 3 or not is_prime(c):
        c -= 1
    return c


def prime_field_candidates(bits, count):
    """The `count` largest primes < 2**bits with p = 3 (mod 4), descending.
    Needed because for a=0 curves, when p = 2 (mod 3) EVERY b gives the
    SAME curve order (the cube map is a bijection mod p, so all nonzero b
    are isomorphic) -- varying b alone can't fix a bad p, so Curve tries
    several DIFFERENT p candidates too."""
    out = []
    c = (1 << bits) - 1
    while len(out) < count and c > 3:
        if c % 4 == 3 and is_prime(c):
            out.append(c)
        c -= 1
    return out


def count_curve_order(p, a, b):
    """Brute-force #E(F_p) for y^2 = x^3 + a*x + b via Euler's criterion
    per x-coordinate (no explicit sqrt needed for counting). O(p) with an
    O(log p) modexp per point. Timings in proposal.md."""
    count = 1  # point at infinity
    for x in range(p):
        rhs = (x * x * x + a * x + b) % p
        if rhs == 0:
            count += 1
        else:
            ls = pow(rhs, (p - 1) // 2, p)
            if ls == 1:
                count += 2
    return count


def factorize(n):
    """Trial division -- fine at these sizes (n has at most ~24 bits in
    this module's rungs, sqrt(n) trial division is fast)."""
    factors = {}
    d = 2
    while d * d <= n:
        while n % d == 0:
            factors[d] = factors.get(d, 0) + 1
            n //= d
        d += 1
    if n > 1:
        factors[n] = factors.get(n, 0) + 1
    return factors


# --- Jacobian-coordinate arithmetic, a=0 curves (untraced setup path) ---

def _jac_double(P, p, a=0):
    """a=0 default reproduces the original secp256k1-shape formula
    unchanged; a != 0 (e.g. P-256's a = p-3, see p256_trace.py) adds the
    a*Z1^4 term the general Weierstrass doubling formula needs. Backward-
    compatible extension, not a behavior change for any existing a=0 caller."""
    X1, Y1, Z1 = P
    if Y1 == 0:
        return (0, 0, 0)
    S = (4 * X1 * Y1 * Y1) % p
    M = (3 * X1 * X1 + a * pow(Z1, 4, p)) % p
    X3 = (M * M - 2 * S) % p
    Y3 = (M * (S - X3) - 8 * pow(Y1, 4, p)) % p
    Z3 = (2 * Y1 * Z1) % p
    return (X3, Y3, Z3)


def _jac_add(P, Q, p, a=0):
    """Point addition is a-independent EXCEPT for the P==Q fallback to
    doubling, which needs a -- threaded through for that case only."""
    X1, Y1, Z1 = P
    X2, Y2, Z2 = Q
    if Z1 == 0:
        return Q
    if Z2 == 0:
        return P
    Z1Z1 = (Z1 * Z1) % p
    Z2Z2 = (Z2 * Z2) % p
    U1 = (X1 * Z2Z2) % p
    U2 = (X2 * Z1Z1) % p
    S1 = (Y1 * Z2 * Z2Z2) % p
    S2 = (Y2 * Z1 * Z1Z1) % p
    if U1 == U2:
        if S1 != S2:
            return (0, 0, 0)
        return _jac_double(P, p, a=a)
    H = (U2 - U1) % p
    R = (S2 - S1) % p
    H2 = (H * H) % p
    H3 = (H2 * H) % p
    X3 = (R * R - H3 - 2 * U1 * H2) % p
    Y3 = (R * (U1 * H2 - X3) - S1 * H3) % p
    Z3 = (H * Z1 * Z2) % p
    return (X3, Y3, Z3)


def jac_scalar_mult(k, P, p, a=0):
    """Untraced scalar mult, right-to-left, Jacobian coords. Handles
    k == 0 (returns the point at infinity) since this is used for setup
    (cofactor clearing) where that can legitimately happen. a=0 default
    backward-compatible; a != 0 needed for P-256 (see p256_trace.py)."""
    Qx, Qy, Qz = 0, 0, 0
    Px, Py, Pz = P[0], P[1], 1
    kk = k
    while kk > 0:
        if kk & 1:
            Qx, Qy, Qz = _jac_add((Qx, Qy, Qz), (Px, Py, Pz), p, a=a)
        Px, Py, Pz = _jac_double((Px, Py, Pz), p, a=a)
        kk >>= 1
    return (Qx, Qy, Qz)


def jac_to_affine(P, p):
    X, Y, Z = P
    if Z == 0:
        return None  # point at infinity
    z_inv = pow(Z, -1, p)
    z_inv2 = (z_inv * z_inv) % p
    z_inv3 = (z_inv2 * z_inv) % p
    return ((X * z_inv2) % p, (Y * z_inv3) % p)


def affine_scalar_mult(k, P, p, a=0):
    return jac_to_affine(jac_scalar_mult(k, P, p, a=a), p)


def point_on_curve(P, p, b):
    x, y = P
    return (y * y - (x ** 3 + b)) % p == 0  # a == 0


class Curve:
    """A small curve, fully constructed and self-describing. p, b: the field
    prime and curve constant (a=0 always). N: full group order (brute-force
    counted). n: the prime subgroup order used for ECDSA. h: cofactor
    (N == h*n). G: a generator of order exactly n."""

    def __init__(self, bits, seed=0):
        self.bits = bits
        rng = random.Random(seed)
        for p_try in prime_field_candidates(bits, count=25):
            for b_try in range(1, 12):
                if (27 * b_try * b_try) % p_try == 0:
                    continue  # singular curve, skip (a==0 so 4a^3+27b^2 = 27b^2)
                N = count_curve_order(p_try, 0, b_try)
                factors = factorize(N)
                n = max(factors)
                if n < p_try // 4:
                    continue  # subgroup too small to be a useful rung, try another (p, b)
                h = N // n
                G = self._find_generator(p_try, b_try, h, n, rng)
                if G is not None:
                    self.p, self.b, self.N, self.n, self.h, self.G = p_try, b_try, N, n, h, G
                    return
        raise RuntimeError(f"could not construct a usable curve at bits={bits}")

    @staticmethod
    def _find_generator(p, b, h, n, rng):
        for _ in range(200):
            x = rng.randrange(1, p)
            rhs = (x * x * x + b) % p
            if rhs == 0:
                continue
            if pow(rhs, (p - 1) // 2, p) != 1:
                continue  # not a QR, no y for this x
            y = pow(rhs, (p + 1) // 4, p)  # valid since p = 3 mod 4
            P = (x, y)
            assert point_on_curve(P, p, b)
            G = jac_to_affine(jac_scalar_mult(h, P, p), p)
            if G is None:
                continue  # landed on infinity, retry
            # order(G) divides n (n prime) and G != infinity -> order is exactly n
            assert jac_to_affine(jac_scalar_mult(n, G, p), p) is None
            return G
        return None

    def __repr__(self):
        return f"Curve(bits={self.bits}, p={self.p}, b={self.b}, n={self.n}, h={self.h})"


# --- modular inverse, extended Euclidean algorithm (the TRACED generator's
# method -- deliberately different from the untraced path's pow(x,-1,p)) ---

def _ext_gcd(a, b):
    old_r, r = a, b
    old_s, s = 1, 0
    while r != 0:
        q = old_r // r
        old_r, r = r, old_r - q * r
        old_s, s = s, old_s - q * s
    return old_r, old_s


def mod_inverse_euclid(a, p):
    a = a % p
    g, x = _ext_gcd(a, p)
    assert g == 1, f"{a} has no inverse mod {p}"
    return x % p


# --- traced (word-scale, line-by-line) point arithmetic ---
# Each formula is an ordered list of (name, op_type, fn(vals)->int); fn
# reads only NAMES ALREADY IN vals (earlier lines or the op's own x1/y1
# [/x2/y2] seed), so genuine evaluation, tamper-and-cascade, and
# printed-value-recompute-check are all the SAME walk over the list --
# see eval_formula / check_formula.

def double_formula(p):
    return [
        ("x1sq_raw", "multiplication", lambda v: v["x1"] * v["x1"]),
        ("x1sq", "reduction", lambda v: v["x1sq_raw"] % p),
        ("numerator_raw", "multiplication", lambda v: 3 * v["x1sq"]),
        ("numerator", "reduction", lambda v: v["numerator_raw"] % p),
        ("denominator", "addition", lambda v: (v["y1"] + v["y1"]) % p),
        ("inv", "inverse-check", lambda v: mod_inverse_euclid(v["denominator"], p)),
        ("lam_raw", "multiplication", lambda v: v["numerator"] * v["inv"]),
        ("lam", "reduction", lambda v: v["lam_raw"] % p),
        ("lamsq_raw", "multiplication", lambda v: v["lam"] * v["lam"]),
        ("lamsq", "reduction", lambda v: v["lamsq_raw"] % p),
        ("two_x1", "addition", lambda v: (v["x1"] + v["x1"]) % p),
        ("x3", "addition", lambda v: (v["lamsq"] - v["two_x1"]) % p),
        ("diff", "addition", lambda v: (v["x1"] - v["x3"]) % p),
        ("t2_raw", "multiplication", lambda v: v["lam"] * v["diff"]),
        ("t2", "reduction", lambda v: v["t2_raw"] % p),
        ("y3", "addition", lambda v: (v["t2"] - v["y1"]) % p),
    ]


def add_formula(p):
    return [
        ("numerator", "addition", lambda v: (v["y2"] - v["y1"]) % p),
        ("denominator", "addition", lambda v: (v["x2"] - v["x1"]) % p),
        ("inv", "inverse-check", lambda v: mod_inverse_euclid(v["denominator"], p)),
        ("lam_raw", "multiplication", lambda v: v["numerator"] * v["inv"]),
        ("lam", "reduction", lambda v: v["lam_raw"] % p),
        ("lamsq_raw", "multiplication", lambda v: v["lam"] * v["lam"]),
        ("lamsq", "reduction", lambda v: v["lamsq_raw"] % p),
        ("t3", "addition", lambda v: (v["lamsq"] - v["x1"]) % p),
        ("x3", "addition", lambda v: (v["t3"] - v["x2"]) % p),
        ("diff", "addition", lambda v: (v["x1"] - v["x3"]) % p),
        ("t2_raw", "multiplication", lambda v: v["lam"] * v["diff"]),
        ("t2", "reduction", lambda v: v["t2_raw"] % p),
        ("y3", "addition", lambda v: (v["t2"] - v["y1"]) % p),
    ]


def eval_formula(formula, seed_vals, tamper_name=None, tamper_bit=None):
    """Evaluate a formula genuinely, or with one named line tampered (bit
    flipped) -- every LATER line in the SAME formula is then computed from
    the tampered value automatically, since each fn reads from vals."""
    vals = dict(seed_vals)
    records = []
    for name, typ, fn in formula:
        val = fn(vals)
        if name == tamper_name:
            val = val ^ (1 << tamper_bit)
        vals[name] = val
        records.append({"name": name, "type": typ, "value": val})
    return vals, records


def check_formula(formula, seed_vals, records):
    """Recompute every line from EARLIER PRINTED values (seeded from
    records, never from ground truth) and return the names that don't
    match their recomputation."""
    vals = dict(seed_vals)
    bad = []
    for (name, typ, fn), rec in zip(formula, records):
        expected = fn(vals)
        if expected != rec["value"]:
            bad.append(name)
        vals[rec["name"]] = rec["value"]
    return bad


class SmallFieldCollision(Exception):
    """Raised when a traced ADD would need to add a point to itself or to
    its negation (x1 == x2) -- the toy-scale addition formula (built for
    two DISTINCT points, matching what a real trace renders) doesn't cover
    that case, and at these small field sizes it is a real, non-negligible
    event during the ladder (unlike real 256-bit ECDSA, where n is
    astronomically larger than any collision probability). Callers catch
    this and resample the signature -- see generate_genuine/generate_tampered.
    """


def run_point_op(kind, p, x1, y1, x2=None, y2=None, tamper_name=None, tamper_bit=None):
    seed = {"x1": x1, "y1": y1}
    if kind == "add":
        if x1 == x2:
            raise SmallFieldCollision(f"x1 == x2 == {x1}, addition formula needs distinct points")
        seed.update({"x2": x2, "y2": y2})
        formula = add_formula(p)
    else:
        if y1 == 0:
            raise SmallFieldCollision("y1 == 0, a 2-torsion point -- doubling formula divides by 2*y1")
        formula = double_formula(p)
    vals, records = eval_formula(formula, seed, tamper_name, tamper_bit)
    return {"kind": kind, "seed": seed, "formula": formula, "records": records,
            "x3": vals["x3"], "y3": vals["y3"]}


def run_ladder(scalar, P, p, tamper_at=None):
    """Left-to-right double-and-add, MSB consumed by initializing R=P (no
    recorded op, matching sha256_trace's own convention for consuming the
    leading bit). tamper_at: optional (op_idx, step_name, bit), op_idx
    0-based within THIS ladder."""
    bits = bin(scalar)[2:]
    x, y = P
    ops = []
    for bit in bits[1:]:
        idx = len(ops)
        tn, tb = (tamper_at[1], tamper_at[2]) if (tamper_at and tamper_at[0] == idx) else (None, None)
        op = run_point_op("double", p, x, y, tamper_name=tn, tamper_bit=tb)
        ops.append(op)
        x, y = op["x3"], op["y3"]
        if bit == "1":
            idx = len(ops)
            tn, tb = (tamper_at[1], tamper_at[2]) if (tamper_at and tamper_at[0] == idx) else (None, None)
            op = run_point_op("add", p, x, y, P[0], P[1], tamper_name=tn, tamper_bit=tb)
            ops.append(op)
            x, y = op["x3"], op["y3"]
    return ops, (x, y)


# --- signing (untraced setup) and the traced verification trace ---

def ecdsa_sign(curve, d, z, k):
    """Untraced (Jacobian), used only to construct a genuine signature to
    then verify/trace. R = k*G; r = Rx mod n; s = k^-1*(z + r*d) mod n."""
    R = affine_scalar_mult(k, curve.G, curve.p)
    assert R is not None
    r = R[0] % curve.n
    assert r != 0
    k_inv = pow(k, -1, curve.n)
    s = (k_inv * (z + r * d)) % curve.n
    assert s != 0
    return r, s


def verify_reference(curve, Q, r, s, z):
    """Independent reference verify: Jacobian arithmetic, built-in
    pow(x,-1,n)/pow(x,-1,p), NOT the traced line-by-line path. Returns
    (valid, v)."""
    if not (1 <= r < curve.n and 1 <= s < curve.n):
        return False, None
    w = pow(s, -1, curve.n)
    u1 = (z * w) % curve.n
    u2 = (r * w) % curve.n
    P1 = jac_scalar_mult(u1, curve.G, curve.p)
    P2 = jac_scalar_mult(u2, Q, curve.p)
    if P1[2] == 0 and P2[2] == 0:
        return False, None
    R = jac_to_affine(P1, curve.p) if P2[2] == 0 else (
        jac_to_affine(P2, curve.p) if P1[2] == 0 else jac_to_affine(_jac_add(P1, P2, curve.p), curve.p))
    if R is None:
        return False, None
    v = R[0] % curve.n
    return v == r, v


def generate_verify_trace(curve, Q, r, s, z, tamper=None):
    """The main (traced) generator: the full ECDSA verification algorithm,
    decomposed into word-scale checkable lines, per the op-counting
    convention. tamper: optional dict {"section": "header"|"ladder1"|
    "ladder2"|"final_add"|"v", "op_idx": int (ignored for header/v),
    "step_name": str, "bit": int}. u1/u2 are guaranteed nonzero by the
    caller (generate_genuine/generate_tampered resample z/k otherwise),
    so neither ladder ever needs to handle the point at infinity.
    """
    p, n = curve.p, curve.n
    ht = tamper if (tamper and tamper["section"] == "header") else None

    def h_tamper(name):
        return (tamper["step_name"], tamper["bit"]) if (ht and tamper["step_name"] == name) else (None, None)

    header = []
    w = mod_inverse_euclid(s, n)
    tn, tb = h_tamper("w")
    if tn:
        w ^= (1 << tb)
    header.append({"name": "w", "type": "inverse-check", "value": w})

    u1_raw = z * w
    tn, tb = h_tamper("u1_raw")
    if tn:
        u1_raw ^= (1 << tb)
    header.append({"name": "u1_raw", "type": "multiplication", "value": u1_raw})
    u1 = u1_raw % n
    tn, tb = h_tamper("u1")
    if tn:
        u1 ^= (1 << tb)
    header.append({"name": "u1", "type": "reduction", "value": u1})

    u2_raw = r * w
    tn, tb = h_tamper("u2_raw")
    if tn:
        u2_raw ^= (1 << tb)
    header.append({"name": "u2_raw", "type": "multiplication", "value": u2_raw})
    u2 = u2_raw % n
    tn, tb = h_tamper("u2")
    if tn:
        u2 ^= (1 << tb)
    header.append({"name": "u2", "type": "reduction", "value": u2})

    assert u1 != 0 and u2 != 0, "u1/u2 landed on 0 -- caller must resample"

    l1_tamper = (tamper["op_idx"], tamper["step_name"], tamper["bit"]) \
        if (tamper and tamper["section"] == "ladder1") else None
    ladder1_ops, P1 = run_ladder(u1, curve.G, p, tamper_at=l1_tamper)

    l2_tamper = (tamper["op_idx"], tamper["step_name"], tamper["bit"]) \
        if (tamper and tamper["section"] == "ladder2") else None
    ladder2_ops, P2 = run_ladder(u2, Q, p, tamper_at=l2_tamper)

    fa_tn, fa_tb = (tamper["step_name"], tamper["bit"]) if (tamper and tamper["section"] == "final_add") else (None, None)
    final_op = run_point_op("add", p, P1[0], P1[1], P2[0], P2[1], tamper_name=fa_tn, tamper_bit=fa_tb)
    R = (final_op["x3"], final_op["y3"])

    v = R[0] % n
    vt = tamper if (tamper and tamper["section"] == "v") else None
    if vt:
        v ^= (1 << tamper["bit"])
    final = [{"name": "v", "type": "reduction", "value": v}]

    valid = (v == r)

    return {"curve": curve, "Q": Q, "r": r, "s": s, "z": z, "header": header,
            "ladder1_ops": ladder1_ops, "ladder2_ops": ladder2_ops, "final_op": final_op,
            "final": final, "R": R, "v": v, "valid": valid, "tamper": tamper}


def local_consistency_report(trace):
    """Recompute every line from its own declared/printed inputs (never
    ground truth) and return the flagged (section, index, name) triples.
    Genuine -> []. A single line-level tamper -> exactly one entry."""
    curve = trace["curve"]
    p, n = curve.p, curve.n
    bad = []

    n_vals = {}
    checks = [
        ("w", "inverse-check", lambda v: mod_inverse_euclid(trace["s"], n)),
        ("u1_raw", "multiplication", lambda v: trace["z"] * v["w"]),
        ("u1", "reduction", lambda v: v["u1_raw"] % n),
        ("u2_raw", "multiplication", lambda v: trace["r"] * v["w"]),
        ("u2", "reduction", lambda v: v["u2_raw"] % n),
    ]
    for (name, typ, fn), rec in zip(checks, trace["header"]):
        expected = fn(n_vals)
        if expected != rec["value"]:
            bad.append(("header", 0, name))
        n_vals[rec["name"]] = rec["value"]

    def check_ops(ops, section):
        for i, op in enumerate(ops):
            formula = op["formula"]
            flagged = check_formula(formula, op["seed"], op["records"])
            for name in flagged:
                bad.append((section, i, name))

    check_ops(trace["ladder1_ops"], "ladder1")
    check_ops(trace["ladder2_ops"], "ladder2")

    def printed_xy(op):
        """x3/y3 are NOT the last two records (y3 depends on t2, which
        comes after x3 in the formula) -- look them up by name, not
        position."""
        by_name = {rec["name"]: rec["value"] for rec in op["records"]}
        return by_name["x3"], by_name["y3"]

    # final point addition: seed comes from the LAST op's PRINTED output in
    # each ladder.
    P1_seed = printed_xy(trace["ladder1_ops"][-1])
    P2_seed = printed_xy(trace["ladder2_ops"][-1])
    fa_seed = {"x1": P1_seed[0], "y1": P1_seed[1], "x2": P2_seed[0], "y2": P2_seed[1]}
    flagged = check_formula(trace["final_op"]["formula"], fa_seed, trace["final_op"]["records"])
    for name in flagged:
        bad.append(("final_add", 0, name))

    # v is checked against final_op's PRINTED x3 (not recomputed ground truth):
    printed_x3, _ = printed_xy(trace["final_op"])
    if (printed_x3 % n) != trace["final"][0]["value"]:
        bad.append(("v", 0, "v"))

    return bad


# --- generation API ---

def generate_genuine(curve, seed):
    rng = random.Random(seed)
    d = rng.randrange(1, curve.n)
    Q = affine_scalar_mult(d, curve.G, curve.p)
    while True:
        z = rng.randrange(1, curve.n)
        k = rng.randrange(1, curve.n)
        try:
            r, s = ecdsa_sign(curve, d, z, k)
        except AssertionError:
            continue
        w = mod_inverse_euclid(s, curve.n)
        if (z * w) % curve.n == 0 or (r * w) % curve.n == 0:
            continue  # u1 or u2 landed on 0, resample (see module docstring)
        try:
            trace = generate_verify_trace(curve, Q, r, s, z)
        except SmallFieldCollision:
            continue  # see SmallFieldCollision's docstring
        break
    ref_valid, ref_v = verify_reference(curve, Q, r, s, z)
    assert trace["valid"] is True, "genuine signature failed the traced verify"
    assert ref_valid is True and ref_v == trace["v"], "traced verify disagrees with the independent Jacobian reference"
    return trace


def total_line_count(trace):
    return (len(trace["header"])
            + sum(len(op["records"]) for op in trace["ladder1_ops"])
            + sum(len(op["records"]) for op in trace["ladder2_ops"])
            + len(trace["final_op"]["records"])
            + len(trace["final"]))


def _flat_targets(trace):
    """Every (section, op_idx, step_name) tamperable line, in trace order
    -- this IS the tamper-target set per the op-counting convention."""
    targets = []
    for rec in trace["header"]:
        targets.append(("header", 0, rec["name"]))
    for i, op in enumerate(trace["ladder1_ops"]):
        for rec in op["records"]:
            targets.append(("ladder1", i, rec["name"]))
    for i, op in enumerate(trace["ladder2_ops"]):
        for rec in op["records"]:
            targets.append(("ladder2", i, rec["name"]))
    for rec in trace["final_op"]["records"]:
        targets.append(("final_add", 0, rec["name"]))
    for rec in trace["final"]:
        targets.append(("v", 0, rec["name"]))
    return targets


def position_buckets(n_targets):
    third = n_targets / 3
    early_end = round(third)
    middle_end = round(2 * third)
    return {"early": range(0, early_end), "middle": range(early_end, middle_end),
            "late": range(middle_end, n_targets)}


def generate_tampered(curve, seed, bucket):
    rng = random.Random(seed)
    d = rng.randrange(1, curve.n)
    Q = affine_scalar_mult(d, curve.G, curve.p)
    while True:
        z = rng.randrange(1, curve.n)
        k = rng.randrange(1, curve.n)
        try:
            r, s = ecdsa_sign(curve, d, z, k)
        except AssertionError:
            continue
        w = mod_inverse_euclid(s, curve.n)
        if (z * w) % curve.n == 0 or (r * w) % curve.n == 0:
            continue
        try:
            genuine = generate_verify_trace(curve, Q, r, s, z)
        except SmallFieldCollision:
            continue  # see SmallFieldCollision's docstring

        targets = _flat_targets(genuine)
        buckets = position_buckets(len(targets))
        idx = rng.choice(list(buckets[bucket]))
        section, op_idx, step_name = targets[idx]
        bit = rng.randrange(max(curve.p, curve.n).bit_length())
        tamper = {"section": section, "op_idx": op_idx, "step_name": step_name, "bit": bit}
        try:
            tampered = generate_verify_trace(curve, Q, r, s, z, tamper=tamper)
        except SmallFieldCollision:
            continue  # the TAMPER itself induced a collision downstream; resample
        break

    bad = local_consistency_report(tampered)
    assert len(bad) == 1, f"expected exactly one flagged line, got {bad}"
    assert bad[0][0] == section and bad[0][2] == step_name, f"flagged line {bad[0]} != tamper target {tamper}"

    tampered["bucket"] = bucket
    tampered["tamper"] = tamper
    tampered["tamper_target_idx"] = idx
    tampered["n_targets"] = len(targets)
    return tampered


# --- multiplication decomposition, LINEAR not pointwise (used for the
# real-256-bit-scale bridge figure in proposal.md, not part of the small-curve
# traces above, whose field sizes are already small enough not to need
# decomposition at all). Design rule locked by Ram, 2026-07-12: decompose a
# big multiplication into ~n lines for an n-word operand, NOT n^2 --
# grade-school long multiplication, one row per word of ONE operand (the
# full other operand times that single word, treated as one multiplication-
# type line, not decomposed further), plus one running-sum addition line
# per row. This replaces an earlier pointwise (n^2 limb-product) version --
# see plan.md's "decomposition rule: linear, not pointwise" entry for why:
# traces must stay short, and the per-op-type error rate (measured
# separately for multiplication vs addition lines) is what absorbs the
# residual difficulty difference between a multiplication-row line and a
# plain addition line, not the line count itself.

def decompose_multiply_linear(a, b, limb_bits=32):
    """Grade-school long multiplication. Decomposes b into limb_bits-sized
    words (little-endian); each row is (a * one word of b), one
    multiplication-type line, immediately accumulated into a running total
    via one addition-type line. n_limbs words -> 2*n_limbs lines total
    (order n, not n^2). Returns {"b_limbs", "rows", "total"} where rows is
    the ordered [{"type": "multiplication"|"addition", "value": ...}, ...]
    list and total == a*b exactly."""
    base = 1 << limb_bits
    n_limbs = max((b.bit_length() + limb_bits - 1) // limb_bits, 1)
    b_limbs = [(b >> (i * limb_bits)) & (base - 1) for i in range(n_limbs)]
    rows = []
    running_total = 0
    for i, bi in enumerate(b_limbs):
        row_value = a * bi  # ONE line: the full other operand times a single word, not decomposed further
        rows.append({"i": i, "b_limb": bi, "type": "multiplication", "value": row_value})
        running_total = running_total + (row_value << (i * limb_bits))
        rows.append({"i": i, "type": "addition", "value": running_total})
    assert running_total == a * b, "linear decomposition does not reconstruct the true product"
    return {"b_limbs": b_limbs, "rows": rows, "total": running_total}


def pointwise_line_count(a, b, limb_bits=32):
    """Line count the OLD (replaced) pointwise n^2 decomposition would have
    used, for reporting the linear-vs-pointwise ratio only -- not used to
    render or check any trace."""
    n_a = max((a.bit_length() + limb_bits - 1) // limb_bits, 1)
    n_b = max((b.bit_length() + limb_bits - 1) // limb_bits, 1)
    return n_a * n_b


def render_trace(trace, line_numbers=True):
    lines = []
    n_ctr = [0]

    def add(text):
        n_ctr[0] += 1
        lines.append(f"L{n_ctr[0]:04d}: {text}" if line_numbers else text)

    curve = trace["curve"]
    add(f"Toy ECDSA verify, {curve.bits}-bit field p={curve.p}, subgroup order n={curve.n}, "
        f"curve y^2 = x^3 + {curve.b} (a=0), G=({curve.G[0]},{curve.G[1]})")
    add(f"Given: Q=({trace['Q'][0]},{trace['Q'][1]}), signature (r={trace['r']}, s={trace['s']}), "
        f"message hash z={trace['z']} (hash-to-scalar stubbed, z given directly)")
    add("--- header: w, u1, u2 ---")
    for rec in trace["header"]:
        add(f"  [{rec['type']}] {rec['name']} = {rec['value']}")

    def render_ops(ops, label):
        add(f"--- {label} ---")
        for i, op in enumerate(ops):
            add(f"  op {i} [{op['kind'].upper()}] x1={op['seed']['x1']} y1={op['seed']['y1']}"
                + (f" x2={op['seed']['x2']} y2={op['seed']['y2']}" if op["kind"] == "add" else ""))
            for rec in op["records"]:
                add(f"    [{rec['type']}] {rec['name']} = {rec['value']}")

    render_ops(trace["ladder1_ops"], "ladder 1: u1 * G")
    render_ops(trace["ladder2_ops"], "ladder 2: u2 * Q")
    add("--- final point addition: R = P1 + P2 ---")
    add(f"  x1={trace['final_op']['seed']['x1']} y1={trace['final_op']['seed']['y1']} "
        f"x2={trace['final_op']['seed']['x2']} y2={trace['final_op']['seed']['y2']}")
    for rec in trace["final_op"]["records"]:
        add(f"    [{rec['type']}] {rec['name']} = {rec['value']}")
    add("--- final ---")
    for rec in trace["final"]:
        add(f"  [{rec['type']}] {rec['name']} = {rec['value']}")
    # No printed "v == r" comparison line here, deliberately: v is printed
    # above (the last "final" record) and r is printed in the header ("Given:
    # ... signature (r=...)"), so the model has both values and must do the
    # comparison itself. An earlier version printed the boolean result
    # directly, which leaked the verdict (~98.7% correlated with GENUINE/
    # TAMPERED per the adversarial audit, confirmed 2026-07-12) -- removed
    # per plan.md's "verdict-leak fix" entry. RENDERER_VERSION marks traces
    # rendered after this fix.
    return "\n".join(lines)


RENDERER_VERSION = "v2-no-verdict-leak-2026-07-12"


if __name__ == "__main__":
    import time

    rng = random.Random(0)
    ok = all(mod_inverse_euclid(a, 251) == pow(a, -1, 251) for a in (rng.randrange(1, 251) for _ in range(50)))
    print(f"mod_inverse_euclid matches pow(x,-1,p) over 50 random values: {ok}")

    a_t, b_t = rng.randrange(1 << 256), rng.randrange(1 << 256)
    d = decompose_multiply_linear(a_t, b_t)
    n_lines_linear = len(d["rows"])
    n_lines_pointwise = pointwise_line_count(a_t, b_t)
    print(f"decompose_multiply_linear reconstructs a*b exactly: {d['total'] == a_t * b_t}")
    print(f"  256-bit x 256-bit multiply, 32-bit words: linear = {n_lines_linear} lines "
          f"({len(d['b_limbs'])} words), pointwise (replaced) would be {n_lines_pointwise} lines "
          f"-- ratio {n_lines_pointwise / n_lines_linear:.1f}x")

    for bits in (8, 12, 16):
        t0 = time.time()
        curve = Curve(bits, seed=1)
        dt = time.time() - t0
        print(f"\n[bits={bits}] {curve} (constructed in {dt:.3f}s)")

        for seed in range(3):
            g = generate_genuine(curve, seed=seed)
            n_lines = total_line_count(g)
            bad = local_consistency_report(g)
            print(f"  genuine seed={seed}: valid={g['valid']}, lines={n_lines}, "
                  f"local_consistency_report empty: {bad == []}")

        # negative self-test: corrupt a signature, confirm verify fails
        g0 = generate_genuine(curve, seed=0)
        bad_s = (g0["s"] + 1) % curve.n or 1
        ref_valid, _ = verify_reference(curve, g0["Q"], g0["r"], bad_s, g0["z"])
        print(f"  corrupted-signature self-test (s+1): reference verify returns False: {ref_valid is False}")

        for bucket in ("early", "middle", "late"):
            t = generate_tampered(curve, seed=100, bucket=bucket)
            print(f"  tampered[{bucket}]: section={t['tamper']['section']} op_idx={t['tamper']['op_idx']} "
                  f"step={t['tamper']['step_name']}, valid={t['valid']} (expect False), "
                  f"exactly-one-flag invariant: OK (asserted inside generate_tampered)")

    curve8 = Curve(8, seed=1)
    g8 = generate_genuine(curve8, seed=0)
    rendered = render_trace(g8)
    print(f"\nbits=8 rendered trace: {len(rendered)} chars, ~{len(rendered)//4} tokens (rough estimate), "
          f"{total_line_count(g8)} op lines")
