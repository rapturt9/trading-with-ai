"""Deterministic SHA-256 trace generator and single-bit tamper injector.

Pure local computation, no API calls, no cost. This is the harness's
foundation: it must be provably correct against Python's own hashlib
before a single dollar is spent calling a model.

Design: one 64-byte (single-block) message, full message schedule
(W[0..63]) and all compression rounds rendered with explicit values,
so a tamper can be injected at any specific intermediate word and
everything downstream is recomputed from that point, exactly like
the chippy studies' "one clean planted inconsistency, code-rendered"
design.

n_rounds defaults to 64 (real, standard SHA-256, verified against
hashlib). n_rounds < 64 is a non-standard reduced-round variant used
only for the length ablation (does detection accuracy scale with how
many rounds a model has to track?); it is NOT a real hash and is
never compared against hashlib.
"""

import hashlib
import random

MASK32 = 0xFFFFFFFF

K = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]

H0 = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19]


def rotr(x, n):
    return ((x >> n) | (x << (32 - n))) & MASK32


def pad_single_block(msg_bytes):
    """Pad a message under 56 bytes into exactly one 64-byte block."""
    assert len(msg_bytes) < 56, "message must fit in a single block with room for padding"
    bit_len = len(msg_bytes) * 8
    padded = msg_bytes + b"\x80"
    padded += b"\x00" * (56 - len(padded))
    padded += bit_len.to_bytes(8, "big")
    assert len(padded) == 64
    return padded


def compute_message_schedule(block):
    W = [int.from_bytes(block[i * 4:i * 4 + 4], "big") for i in range(16)]
    for t in range(16, 64):
        s0 = rotr(W[t - 15], 7) ^ rotr(W[t - 15], 18) ^ (W[t - 15] >> 3)
        s1 = rotr(W[t - 2], 17) ^ rotr(W[t - 2], 19) ^ (W[t - 2] >> 10)
        W.append((W[t - 16] + s0 + W[t - 7] + s1) & MASK32)
    return W[:64] if len(W) == 64 else W


def compress(W, tamper_step=None, tamper_bit=None, n_rounds=64, init_state=None, start_round=0):
    """Run n_rounds compression rounds (64 = real SHA-256) starting at
    absolute round index start_round. If tamper_step is set, flip
    tamper_bit in the working-variable state produced by that round before
    continuing, so everything after is recomputed from the tampered state
    (self-consistent downstream, exactly like the original chippy design).

    Every round records not just the combined temp1/temp2 but the
    intermediate pairwise sums building up to temp1 (h+S1, +ch, +K[t]),
    so the trace can show "smaller operations before bigger ones" instead
    of one opaque 5-term sum.

    init_state: the 8 working words to start the first round from (defaults
    to H0, the single-block case). Passing the previous block's `final`
    here is what lets a caller chain multiple blocks (Merkle-Damgard
    construction) without duplicating this function; added for
    verification-frontier's multi-block SHA generator, backward-compatible
    (default unchanged).

    start_round: the absolute round index (indexes into K/W) that the loop
    begins at; range(n_rounds) becomes range(start_round, start_round +
    n_rounds). Lets a caller resume compression mid-block from an
    already-tampered round's shifted state -- recorded round["t"] stays the
    true absolute index -- instead of duplicating this loop body to cascade
    a within-round tamper class (bitwise/schedule-word/addition, not just
    the final new_a) through the rest of the block; added for
    verification-frontier's tamper-class stratification. Backward-compatible
    (default 0 reproduces the original range(n_rounds)).

    Returns the list of per-round states and the final hash words (final
    is only a real SHA-256 digest input when n_rounds == 64, start_round ==
    0, and, for a chained call, init_state is the prior block's final).
    """
    assert 1 <= n_rounds <= 64
    assert 0 <= start_round and start_round + n_rounds <= 64
    if init_state is None:
        init_state = H0
    a, b, c, d, e, f, g, h = init_state
    rounds = []
    for t in range(start_round, start_round + n_rounds):
        S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)
        ch = (e & f) ^ (~e & g) & MASK32
        step1 = (h + S1) & MASK32
        step2 = (step1 + ch) & MASK32
        step3 = (step2 + K[t]) & MASK32
        temp1 = (step3 + W[t]) & MASK32
        S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)
        maj = (a & b) ^ (a & c) ^ (b & c)
        temp2 = (S0 + maj) & MASK32

        new_h, new_g, new_f = g, f, e
        new_e = (d + temp1) & MASK32
        new_d, new_c, new_b = c, b, a
        new_a = (temp1 + temp2) & MASK32

        if tamper_step is not None and t == tamper_step:
            # flip one bit in the freshly computed 'a' (arbitrary choice of
            # which working variable to hit; the stratified early/mid/late
            # position comes from which round t is chosen)
            new_a ^= (1 << tamper_bit)

        rounds.append({
            "t": t, "K": K[t], "W": W[t],
            "e_in": e, "f_in": f, "g_in": g, "h_in": h,
            "a_in": a, "b_in": b, "c_in": c, "d_in": d,
            "S1": S1, "ch": ch,
            "step1": step1, "step2": step2, "step3": step3, "temp1": temp1,
            "S0": S0, "maj": maj, "temp2": temp2,
            "a": new_a, "b": new_b, "c": new_c, "d": new_d,
            "e": new_e, "f": new_f, "g": new_g, "h": new_h,
        })
        a, b, c, d, e, f, g, h = new_a, new_b, new_c, new_d, new_e, new_f, new_g, new_h

    final = [
        (init_state[0] + a) & MASK32, (init_state[1] + b) & MASK32,
        (init_state[2] + c) & MASK32, (init_state[3] + d) & MASK32,
        (init_state[4] + e) & MASK32, (init_state[5] + f) & MASK32,
        (init_state[6] + g) & MASK32, (init_state[7] + h) & MASK32,
    ]
    return rounds, final


def hash_hex(final_words):
    return "".join(f"{w:08x}" for w in final_words)


def generate_genuine(seed, n_rounds=64):
    rng = random.Random(seed)
    msg = bytes(rng.randrange(32, 127) for _ in range(50))  # printable-ish ASCII, 50 bytes
    block = pad_single_block(msg)
    W = compute_message_schedule(block)
    rounds, final = compress(W, n_rounds=n_rounds)
    digest = hash_hex(final)
    if n_rounds == 64:
        assert digest == hashlib.sha256(msg).hexdigest(), "trace generator disagrees with hashlib"
    return {"message": msg, "W": W[:n_rounds], "rounds": rounds, "final": final,
            "digest": digest, "n_rounds": n_rounds}


def position_buckets(n_rounds=64):
    """Proportional early/middle/late thirds of n_rounds. At n_rounds=64
    this reproduces the original fixed ranges (0-20 / 21-42 / 43-63)."""
    third = n_rounds / 3
    early_end = round(third)
    middle_end = round(2 * third)
    return {
        "early": range(0, early_end),
        "middle": range(early_end, middle_end),
        "late": range(middle_end, n_rounds),
    }


POSITION_BUCKETS = position_buckets(64)  # backward-compatible module-level default


def generate_tampered(seed, bucket, n_rounds=64):
    rng = random.Random(seed)
    msg = bytes(rng.randrange(32, 127) for _ in range(50))
    block = pad_single_block(msg)
    W = compute_message_schedule(block)

    buckets = position_buckets(n_rounds)
    tamper_step = rng.choice(list(buckets[bucket]))
    tamper_bit = rng.randrange(32)

    genuine_rounds, genuine_final = compress(W, n_rounds=n_rounds)
    tampered_rounds, tampered_final = compress(W, tamper_step=tamper_step, tamper_bit=tamper_bit, n_rounds=n_rounds)

    genuine_digest = hash_hex(genuine_final)
    tampered_digest = hash_hex(tampered_final)
    if n_rounds == 64:
        assert genuine_digest == hashlib.sha256(msg).hexdigest()
    assert tampered_digest != genuine_digest, "tamper did not propagate to final hash"
    # prefix must be identical up to (not including) the tamper step
    assert genuine_rounds[:tamper_step] == tampered_rounds[:tamper_step], "tamper leaked upstream"
    assert genuine_rounds[tamper_step:] != tampered_rounds[tamper_step:], "tamper did not propagate downstream"

    return {
        "message": msg, "W": W[:n_rounds], "rounds": tampered_rounds, "final": tampered_final,
        "digest": tampered_digest, "tamper_step": tamper_step, "tamper_bit": tamper_bit,
        "bucket": bucket, "n_rounds": n_rounds,
    }


def _fmt_word(x, base):
    """hex: 8 hex chars. binary: 32 bits grouped in nibbles, e.g. '0110 1010 ...'."""
    if base == "hex":
        return f"{x:08x}"
    if base == "binary":
        bits = f"{x:032b}"
        return " ".join(bits[i:i + 4] for i in range(0, 32, 4))
    raise ValueError(f"unknown base {base!r}")


class _Liner:
    """Appends lines to a list, optionally prefixing a running line number
    so the model can cite an exact line ('see L0042') instead of only a
    round number, per the affordance that verification should be easy to
    do precisely."""
    def __init__(self, line_numbers):
        self.lines = []
        self.line_numbers = line_numbers
        self.n = 0

    def add(self, text):
        self.n += 1
        self.lines.append(f"L{self.n:04d}: {text}" if self.line_numbers else text)

    def blank(self):
        self.lines.append("")

    def text(self):
        return "\n".join(self.lines)


def render_trace(trace, base="hex", decompose_add=True, line_numbers=True):
    """Render a trace dict into the exact text a model would see.

    base: "hex" (compact) or "binary" (every bitwise op trivially visible,
    much more verbose). decompose_add: show the 5-term temp1 sum as three
    small pairwise additions building up to it (verify small ops before
    the big one) instead of one combined line. line_numbers: prefix every
    line with a running counter so the model can cite an exact line.
    """
    w = lambda x: _fmt_word(x, base)
    L = _Liner(line_numbers)

    L.add(f"Message (hex): {trace['message'].hex()}")
    n_rounds = trace["n_rounds"]
    L.add(f"Message schedule W[0..{n_rounds - 1}] ({base}):")
    for i, word in enumerate(trace["W"]):
        L.add(f"  W[{i}] = {w(word)}")
    L.blank()
    if n_rounds == 64:
        L.add("Compression, 64 rounds (standard single-block SHA-256). "
              "Each round shows every intermediate value, smaller operations before "
              "the larger sums they feed into:")
    else:
        L.add(f"Compression, {n_rounds} rounds (REDUCED-ROUND variant, NOT standard "
              "SHA-256; used only to test whether trace length affects verification "
              "difficulty). Each round shows every intermediate value, smaller "
              "operations before the larger sums they feed into:")
    for r in trace["rounds"]:
        L.add(f"round {r['t']} (K[{r['t']}]={w(r['K'])}, W[{r['t']}]={w(r['W'])}):")
        L.add(f"  inputs: a={w(r['a_in'])} b={w(r['b_in'])} c={w(r['c_in'])} d={w(r['d_in'])} "
              f"e={w(r['e_in'])} f={w(r['f_in'])} g={w(r['g_in'])} h={w(r['h_in'])}")
        L.add(f"  S1 = ROTR(e,6) xor ROTR(e,11) xor ROTR(e,25) = {w(r['S1'])}")
        L.add(f"  ch = (e and f) xor (not e and g) = {w(r['ch'])}")
        if decompose_add:
            L.add(f"  step1 = h + S1 mod 2^32 = {w(r['step1'])}")
            L.add(f"  step2 = step1 + ch mod 2^32 = {w(r['step2'])}")
            L.add(f"  step3 = step2 + K[{r['t']}] mod 2^32 = {w(r['step3'])}")
            L.add(f"  temp1 = step3 + W[{r['t']}] mod 2^32 = {w(r['temp1'])}")
        else:
            L.add(f"  temp1 = h + S1 + ch + K[{r['t']}] + W[{r['t']}] mod 2^32 = {w(r['temp1'])}")
        L.add(f"  S0 = ROTR(a,2) xor ROTR(a,13) xor ROTR(a,22) = {w(r['S0'])}")
        L.add(f"  maj = (a and b) xor (a and c) xor (b and c) = {w(r['maj'])}")
        L.add(f"  temp2 = S0 + maj mod 2^32 = {w(r['temp2'])}")
        L.add(f"  new a = temp1 + temp2 mod 2^32 = {w(r['a'])}")
        L.add(f"  new e = d + temp1 mod 2^32 = {w(r['e'])}")
        L.add(f"  (b,c,d,f,g,h shift: b={w(r['b'])} c={w(r['c'])} d={w(r['d'])} "
              f"f={w(r['f'])} g={w(r['g'])} h={w(r['h'])})")
    L.blank()
    L.add(f"Final digest: {trace['digest']}")
    return L.text()


def _fmt_dec(x):
    """Decimal rendering of a 32-bit word (the arithmetic channel LLMs are
    most reliable in, per the Phase 3 redesign)."""
    return str(x)


def render_dual(trace, line_numbers=True, binary_bitops=True, binary_new=True,
                decimal_additions=True, binary_state=True, tag_op_types=False):
    """Phase 3 dual renderer: binary for bitwise ops, DECIMAL for additions.

    Sibling of render_trace(); every lever is a parameter. Per round it prints:
      - the 8 input state words a_in..h_in, each in binary AND decimal (or
        decimal-only if binary_state is False);
      - the 4 bitwise results S1, ch, S0, maj, in binary (and decimal if
        binary_bitops) -- these are checked bit-by-bit, so binary is primary;
      - the 7 modular additions step1/step2/step3/temp1/temp2/new_a/new_e in
        DECIMAL (decimal_additions), with new_a and new_e ALSO in binary
        (binary_new) because they feed the next round's bitwise ops;
      - NO shift line: round t+1's input block reprints the state, so the
        chain check survives as a string comparison across rounds.

    binary_state: added for verification-frontier's decimal-densified rung
    (drop the binary column entirely to shrink token count for the SHA
    length-scaling axis); False makes the message schedule W[] and the
    per-round a_in..h_in state words decimal-only too, so with
    binary_bitops=binary_new=False the whole trace is decimal-only.
    Backward-compatible: default True reproduces the original dual output.

    tag_op_types: added for verification-frontier's op-counting convention
    (locked 2026-07-12) -- when True, prefixes each derived-value line with
    its op type ("[bitwise]" for S1/ch/S0/maj, "[addition]" for
    step1/step2/step3/temp1/temp2/new a/new e), matching the tagging
    ecdsa_trace.py's renderer already does, so the per-op-type reliability
    analysis has the same visible tag in both families. Backward-compatible
    (default False reproduces the original untagged output).

    Both representations of every value come from the SAME integer, so binary
    and decimal always agree (including at the tampered value). The tamper (a
    bit flip in one round's new_a, downstream recomputed consistently) leaves
    EXACTLY ONE locally inconsistent line in the whole trace: in the tampered
    round, printed new_a != printed temp1 + printed temp2. No cross-round
    re-derivation is ever needed; every equation is checkable from operands
    printed on earlier lines.
    """
    b = lambda x: _fmt_word(x, "binary")
    d = _fmt_dec
    L = _Liner(line_numbers)
    tag = (lambda t: f"[{t}] ") if tag_op_types else (lambda t: "")

    def dual(x):
        """binary AND decimal, e.g. '0110 ... 0111 = 1779033703'."""
        return f"{b(x)} = {d(x)}"

    sw = dual if binary_state else d

    L.add(f"Message (hex): {trace['message'].hex()}")
    n_rounds = trace["n_rounds"]
    W_label = "binary and decimal" if binary_state else "decimal"
    L.add(f"Message schedule W[0..{n_rounds - 1}] ({W_label}):")
    for i, word in enumerate(trace["W"]):
        L.add(f"  W[{i}] = {sw(word)}")
    L.blank()
    if n_rounds == 64:
        L.add("Compression, 64 rounds (standard single-block SHA-256). Bitwise results "
              "(S1, ch, S0, maj) are shown in binary; additions are shown in decimal; "
              "state words and new_a/new_e are shown in both. Both representations of any "
              "value come from the same integer, so they always agree. Every equation is "
              "checkable from values printed on earlier lines:")
    else:
        L.add(f"Compression, {n_rounds} rounds (REDUCED-ROUND variant, NOT standard "
              "SHA-256; used only to test whether trace length affects verification "
              "difficulty). Bitwise results in binary, additions in decimal, state words "
              "and new_a/new_e in both; both representations always agree.")
    for r in trace["rounds"]:
        L.add(f"round {r['t']} (K[{r['t']}] = {sw(r['K'])}, W[{r['t']}] = {sw(r['W'])}):")
        L.add(f"  a_in = {sw(r['a_in'])}")
        L.add(f"  b_in = {sw(r['b_in'])}")
        L.add(f"  c_in = {sw(r['c_in'])}")
        L.add(f"  d_in = {sw(r['d_in'])}")
        L.add(f"  e_in = {sw(r['e_in'])}")
        L.add(f"  f_in = {sw(r['f_in'])}")
        L.add(f"  g_in = {sw(r['g_in'])}")
        L.add(f"  h_in = {sw(r['h_in'])}")
        s1 = dual(r['S1']) if binary_bitops else d(r['S1'])
        ch = dual(r['ch']) if binary_bitops else d(r['ch'])
        s0 = dual(r['S0']) if binary_bitops else d(r['S0'])
        maj = dual(r['maj']) if binary_bitops else d(r['maj'])
        L.add(f"  {tag('bitwise')}S1 = ROTR(e,6) xor ROTR(e,11) xor ROTR(e,25) = {s1}")
        L.add(f"  {tag('bitwise')}ch = (e and f) xor (not e and g) = {ch}")
        add = d if decimal_additions else (lambda x: dual(x))
        L.add(f"  {tag('addition')}step1 = h_in + S1 mod 2^32 = {add(r['step1'])}")
        L.add(f"  {tag('addition')}step2 = step1 + ch mod 2^32 = {add(r['step2'])}")
        L.add(f"  {tag('addition')}step3 = step2 + K[{r['t']}] mod 2^32 = {add(r['step3'])}")
        L.add(f"  {tag('addition')}temp1 = step3 + W[{r['t']}] mod 2^32 = {add(r['temp1'])}")
        L.add(f"  {tag('bitwise')}S0 = ROTR(a,2) xor ROTR(a,13) xor ROTR(a,22) = {s0}")
        L.add(f"  {tag('bitwise')}maj = (a and b) xor (a and c) xor (b and c) = {maj}")
        L.add(f"  {tag('addition')}temp2 = S0 + maj mod 2^32 = {add(r['temp2'])}")
        new_a = dual(r['a']) if binary_new else add(r['a'])
        new_e = dual(r['e']) if binary_new else add(r['e'])
        L.add(f"  {tag('addition')}new a = temp1 + temp2 mod 2^32 = {new_a}")
        L.add(f"  {tag('addition')}new e = d_in + temp1 mod 2^32 = {new_e}")
    L.blank()
    L.add(f"Final digest: {trace['digest']}")
    return L.text()


def local_consistency_report(trace):
    """Stage-0 verifier: recompute every printed equation from the values the
    renderer prints (the round records), and return the list of equations
    whose printed result does NOT equal the recomputation. For a genuine
    trace this is empty; for a tampered trace it must be EXACTLY the tampered
    round's new_a. Because render_dual prints both bases from the same integer,
    this integer-level check certifies both-base consistency simultaneously.
    """
    bad = []
    prev = None
    for r in trace["rounds"]:
        t = r["t"]
        # chain check: this round's 8 input state words must equal the prior
        # round's 8 output state words (a..h), one-to-one (render_dual reprints
        # the state each round, so the chain is a plain string comparison).
        if prev is not None:
            in_state = (r["a_in"], r["b_in"], r["c_in"], r["d_in"],
                        r["e_in"], r["f_in"], r["g_in"], r["h_in"])
            out_state = (prev["a"], prev["b"], prev["c"], prev["d"],
                         prev["e"], prev["f"], prev["g"], prev["h"])
            if in_state != out_state:
                bad.append((t, "chain_state"))
        # arithmetic checks, each from printed operands only
        checks = {
            "step1": (r["h_in"] + r["S1"]) & MASK32,
            "step2": (r["step1"] + r["ch"]) & MASK32,
            "step3": (r["step2"] + r["K"]) & MASK32,
            "temp1": (r["step3"] + r["W"]) & MASK32,
            "temp2": (r["S0"] + r["maj"]) & MASK32,
            "new_a": (r["temp1"] + r["temp2"]) & MASK32,
            "new_e": (r["d_in"] + r["temp1"]) & MASK32,
        }
        printed = {"step1": r["step1"], "step2": r["step2"], "step3": r["step3"],
                   "temp1": r["temp1"], "temp2": r["temp2"], "new_a": r["a"], "new_e": r["e"]}
        for name, computed in checks.items():
            if computed != printed[name]:
                bad.append((t, name))
        prev = r
    return bad


if __name__ == "__main__":
    import sys
    if "--dry-run" in sys.argv:
        # Phase 3 dry-run: token count of render_dual over all 84 seeded traces,
        # zero network calls. Lazy import of build_dataset to avoid a top-level
        # circular import with run_experiment.
        import tiktoken
        from run_experiment import build_dataset, build_prompt_v2
        items = build_dataset()
        enc_a = tiktoken.get_encoding("cl100k_base")
        try:
            enc_b = tiktoken.get_encoding("o200k_base")
        except Exception:
            enc_b = None
        trace_toks_a, prompt_toks_a, prompt_toks_b = [], [], []
        for item in items:
            txt = render_dual(item["trace"])
            trace_toks_a.append(len(enc_a.encode(txt)))
            prompt = build_prompt_v2(txt)
            prompt_toks_a.append(len(enc_a.encode(prompt)))
            if enc_b is not None:
                prompt_toks_b.append(len(enc_b.encode(prompt)))
        n = len(items)
        print(f"render_dual --dry-run over {n} seeded traces (42 genuine + 42 tampered):")
        print(f"  trace-only tokens  (cl100k): mean {sum(trace_toks_a)//n}, "
              f"min {min(trace_toks_a)}, max {max(trace_toks_a)}")
        print(f"  full prompt tokens (cl100k): mean {sum(prompt_toks_a)//n}, "
              f"min {min(prompt_toks_a)}, max {max(prompt_toks_a)}")
        if enc_b is not None:
            print(f"  full prompt tokens (o200k) : mean {sum(prompt_toks_b)//n}, "
                  f"min {min(prompt_toks_b)}, max {max(prompt_toks_b)}")
        sys.exit(0)

    # local self-test only, no network calls, no cost
    g = generate_genuine(seed=1)
    print("genuine digest matches hashlib:", g["digest"] == hashlib.sha256(g["message"]).hexdigest())

    for bucket in ["early", "middle", "late"]:
        t = generate_tampered(seed=42, bucket=bucket)
        print(f"[{bucket}] tamper at round {t['tamper_step']}, bit {t['tamper_bit']}, "
              f"digest changed: {t['digest'] != hashlib.sha256(t['message']).hexdigest()}")

    # reduced-round variant self-test: internal consistency only (not hashlib)
    for n in (8, 16, 32):
        g_r = generate_genuine(seed=1, n_rounds=n)
        t_r = generate_tampered(seed=42, bucket="middle", n_rounds=n)
        print(f"[n_rounds={n}] genuine rounds recorded: {len(g_r['rounds'])} == {n}: "
              f"{len(g_r['rounds']) == n}, tampered digest differs: "
              f"{t_r['digest'] != g_r['digest']}")

    for base in ("hex", "binary"):
        for decompose in (True, False):
            trace_text = render_trace(g, base=base, decompose_add=decompose)
            print(f"\nRendered genuine trace (base={base}, decompose_add={decompose}): "
                  f"{len(trace_text)} chars, ~{len(trace_text)//4} tokens (rough estimate)")
