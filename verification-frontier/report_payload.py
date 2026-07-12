"""Report-shaped SHA payloads -- Stage 0c, task 2. Builds a message
formatted like a TEE attestation report (measurement, nonce, timestamp
fields) instead of pure random bytes, then hashes it via the EXISTING
sha256_multiblock generator/tamper/render/check machinery (reused via the
`message=` override added there, not duplicated).

Why this matters for the design: `../structure.md`'s TEE mechanism check
is "hash the report (~1k-5k ops) plus one ECDSA verify (~410k-800k) plus
2-3 certificate-chain signatures" -- the SHA family so far has only
hashed arbitrary random bytes. A report-shaped payload is what a model
actually sees in the real mechanism: labeled fields, not an opaque blob,
which is itself relevant to checkability (a labeled field boundary is
something a model could cross-reference, unlike a featureless byte run).
"""

import random

import sha256_multiblock as shamb


def build_report_message(seed, n_blocks):
    """Exactly n_blocks*64-9 bytes (the exact-length convention
    sha256_multiblock.pad_multi_block requires), formatted as labeled
    attestation-report-style fields: MEAS (a measurement placeholder),
    NONCE, TS (timestamp), padded to the exact target length with a
    labeled FILL field so every rung still parses as one coherent report,
    not a truncated one."""
    target_len = n_blocks * 64 - 9
    rng = random.Random(seed)
    meas = rng.randbytes(4).hex()     # 8 hex chars -- a compact measurement placeholder
    nonce = rng.randbytes(4).hex()    # 8 hex chars
    ts = str(1_700_000_000 + rng.randrange(100_000_000))  # a plausible 10-digit unix timestamp

    base = f"MEAS={meas} NONCE={nonce} TS={ts}".encode("ascii")
    assert len(base) <= target_len, (
        f"report base fields ({len(base)} bytes) don't fit target_len={target_len} "
        f"(n_blocks={n_blocks}) -- smallest supported rung is n_blocks=1 (55 bytes)"
    )
    fill_label = b" FILL="
    remaining = target_len - len(base) - len(fill_label)
    assert remaining >= 0, f"no room for a FILL field at n_blocks={n_blocks}"
    fill_hex = rng.randbytes((remaining + 1) // 2).hex()[:remaining]
    message = base + fill_label + fill_hex.encode("ascii")
    assert len(message) == target_len, f"built {len(message)} bytes, expected {target_len}"
    return message


def generate_genuine(seed, n_blocks):
    message = build_report_message(seed, n_blocks)
    return shamb.generate_genuine(seed=seed, n_blocks=n_blocks, message=message)


def generate_tampered(seed, bucket, n_blocks):
    message = build_report_message(seed, n_blocks)
    return shamb.generate_tampered(seed=seed, bucket=bucket, n_blocks=n_blocks, message=message)


if __name__ == "__main__":
    import hashlib

    for n_blocks in (1, 2, 4, 8):
        msg = build_report_message(seed=1, n_blocks=n_blocks)
        print(f"[n_blocks={n_blocks}] report message ({len(msg)} bytes): {msg!r}")

        g = generate_genuine(seed=1, n_blocks=n_blocks)
        ok_digest = g["digest"] == hashlib.sha256(g["message"]).hexdigest()
        ok_clean = shamb.local_consistency_report(g) == []
        print(f"  genuine: digest==hashlib: {ok_digest}, local_consistency_report empty: {ok_clean}")

        for bucket in ("early", "middle", "late"):
            t = generate_tampered(seed=42, bucket=bucket, n_blocks=n_blocks)
            bad = shamb.local_consistency_report(t)
            expected = [(t["tamper_block"], t["tamper_step"], "new_a")]
            digest_changed = t["digest"] != hashlib.sha256(t["message"]).hexdigest()
            print(f"  tampered[{bucket}]: flags=={expected}: {bad == expected}, digest_changed: {digest_changed}")
