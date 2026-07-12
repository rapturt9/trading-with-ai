"""Composite mini-attestation rung -- Stage 0c, task 3. Chains the other
two Stage 0c generators into ONE trace: hash a short report-shaped
payload (report_payload.py), then verify a real P-256 signature fragment
over that digest (p256_trace.py), reusing both unmodified rather than
reimplementing either half.

This is the closest Stage 0 gets to the real TEE-attestation mechanism
in `../structure.md` Section 4 ("hash the report... plus one ECDSA P-256
verify... plus certificate-chain signatures"): a genuinely CHAINED
computation, not two independent traces shown side by side. The tamper-
target set spans both halves; the weighting between them is by real op
count (SHA rounds vs P-256 fragment lines), not an arbitrary 50/50 split.

**Downstream-recompute rule, applied across the seam.** When the SHA half
is tampered, its digest genuinely changes -- so the P-256 half must be
FULLY regenerated from that new digest (a fresh, genuine, valid
signature and fragment over the new z), not left pointing at the old
digest's z. This is the same "everything downstream recomputed
consistently from the tamper" principle used everywhere else in this
project, just applied across a hash-then-sign boundary instead of within
one primitive. When the P-256 half is tampered instead, the SHA half
stays genuine and z stays fixed to its real digest -- only one half ever
carries an inconsistency, so the whole composite trace still has EXACTLY
ONE locally inconsistent line, proven the same way as every other trace
in this project.
"""

import random

import report_payload
import sha256_multiblock as shamb
import p256_trace as p256


def _digest_to_z(digest_hex):
    """A SHA-256 digest is 256 bits; P-256's N is also ~256 bits but
    slightly less than 2**256, so reduce mod N and guard against landing
    on 0 (not part of the tamper-invariant machinery -- this is just
    turning a hash output into a valid ECDSA message-hash integer, the
    same reduction real ECDSA implementations do)."""
    z = int(digest_hex, 16) % p256.N
    return z if z != 0 else 1


def generate_genuine(seed, sha_n_blocks=1, p256_n_ops=2, limb_bits=8):
    sha_seed = seed
    p256_seed = seed + 500_000_007
    sha_trace = report_payload.generate_genuine(seed=sha_seed, n_blocks=sha_n_blocks)
    z = _digest_to_z(sha_trace["digest"])
    p256_gen = p256.generate_genuine_fragment(seed=p256_seed, n_ops=p256_n_ops, limb_bits=limb_bits, z=z)
    return {"sha": sha_trace, "p256": p256_gen, "z": z, "sha_seed": sha_seed, "p256_seed": p256_seed,
            "sha_n_blocks": sha_n_blocks, "p256_n_ops": p256_n_ops, "limb_bits": limb_bits}


def total_line_count(gen):
    """Rough SHA line count (7 addition lines/round, matching the
    established '448 ops/block' convention) plus the real measured P-256
    fragment line count -- used only to WEIGHT which half a tamper lands
    in, not as a rendered claim."""
    sha_lines = gen["sha_n_blocks"] * 64 * 7
    p256_lines = p256.total_line_count(gen["p256"])
    return sha_lines, p256_lines


def local_consistency_report(gen):
    sha_bad = shamb.local_consistency_report(gen["sha"])
    p256_bad = p256.local_consistency_report(gen["p256"]["fragment"], gen["p256"]["limb_bits"])
    return [("sha",) + t for t in sha_bad] + [("p256",) + t for t in p256_bad]


def generate_tampered(seed, bucket, sha_n_blocks=1, p256_n_ops=2, limb_bits=8):
    genuine = generate_genuine(seed, sha_n_blocks, p256_n_ops, limb_bits)
    sha_lines, p256_lines = total_line_count(genuine)
    rng = random.Random(seed * 31_337 + 11)
    half = rng.choices(["sha", "p256"], weights=[sha_lines, p256_lines])[0]

    if half == "sha":
        tampered_sha = report_payload.generate_tampered(seed=genuine["sha_seed"], bucket=bucket,
                                                          n_blocks=sha_n_blocks)
        new_z = _digest_to_z(tampered_sha["digest"])
        # everything downstream of the tampered digest is regenerated FRESH
        # and genuine -- the SHA half carries the tamper, the P-256 half
        # doesn't inherit a second one.
        p256_gen = p256.generate_genuine_fragment(seed=genuine["p256_seed"], n_ops=p256_n_ops,
                                                    limb_bits=limb_bits, z=new_z)
        combined = {"sha": tampered_sha, "p256": p256_gen, "z": new_z,
                    "sha_seed": genuine["sha_seed"], "p256_seed": genuine["p256_seed"],
                    "sha_n_blocks": sha_n_blocks, "p256_n_ops": p256_n_ops, "limb_bits": limb_bits}
        tamper_info = {"half": "sha", "bucket": bucket,
                        "block": tampered_sha["tamper_block"], "round": tampered_sha["tamper_step"]}
    else:
        tampered_p256 = p256.generate_tampered_fragment(seed=genuine["p256_seed"], n_ops=p256_n_ops,
                                                          bucket=bucket, limb_bits=limb_bits, z=genuine["z"])
        combined = {"sha": genuine["sha"], "p256": tampered_p256, "z": genuine["z"],
                    "sha_seed": genuine["sha_seed"], "p256_seed": genuine["p256_seed"],
                    "sha_n_blocks": sha_n_blocks, "p256_n_ops": p256_n_ops, "limb_bits": limb_bits}
        tamper_info = {"half": "p256", "bucket": bucket,
                        "op_idx": tampered_p256["tamper"]["op_idx"],
                        "step_name": tampered_p256["tamper"]["step_name"]}

    bad = local_consistency_report(combined)
    assert len(bad) == 1, f"expected exactly one flagged line across the composite, got {bad}"
    combined["tamper"] = tamper_info
    return combined


def render(gen, tag_op_types=True):
    parts = []
    parts.append("=== Part 1: hash a short report-shaped payload ===")
    parts.append(shamb.render_multiblock(gen["sha"], tag_op_types=tag_op_types))
    parts.append("")
    parts.append(f"=== Bridge: the digest above becomes the message hash for the signature check below ===")
    parts.append(f"z = digest interpreted as a 256-bit integer, reduced mod the P-256 curve order n = {gen['z']}")
    parts.append("")
    parts.append("=== Part 2: verify a real P-256 signature fragment over that digest ===")
    parts.append(p256.render_fragment(gen["p256"], tag_op_types=tag_op_types))
    return "\n".join(parts)


# Audited 2026-07-12 alongside ecdsa_trace.py's verdict-leak fix: this
# composite renderer only concatenates shamb.render_multiblock (prints the
# digest, legitimate input data, not a verdict) and p256.render_fragment
# (confirmed clean, see that module's own audit note) -- no v/r comparison
# is computed or printed anywhere in the composite either. Version marker
# kept in step with the other two renderers for a consistent audit trail.
RENDERER_VERSION = "v2-no-verdict-leak-2026-07-12"


if __name__ == "__main__":
    fails = 0
    for sha_n_blocks in (1,):
        for p256_n_ops in (2, 4):
            g = generate_genuine(seed=1, sha_n_blocks=sha_n_blocks, p256_n_ops=p256_n_ops)
            bad = local_consistency_report(g)
            sha_lines, p256_lines = total_line_count(g)
            print(f"[sha_n_blocks={sha_n_blocks} p256_n_ops={p256_n_ops}] genuine: "
                  f"local_consistency_report empty: {bad == []} (sha~{sha_lines} lines, p256={p256_lines} lines)")
            if bad != []:
                fails += 1

            for bucket in ("early", "middle", "late"):
                for seed in range(6):
                    t = generate_tampered(seed=seed * 101 + 3, bucket=bucket,
                                           sha_n_blocks=sha_n_blocks, p256_n_ops=p256_n_ops)
                    bad = local_consistency_report(t)
                    ok = len(bad) == 1
                    if not ok:
                        fails += 1
                        print(f"  FAIL bucket={bucket} seed={seed}: flags={bad}")
                print(f"  [{bucket}] 6 seeds: exactly-one-flag across the composite holds")

    print(f"\nTOTAL FAILS: {fails}")

    r = render(generate_genuine(seed=1, sha_n_blocks=1, p256_n_ops=2))
    print(f"\nRendered composite (sha_n_blocks=1, p256_n_ops=2): {len(r)} chars, ~{len(r)//4} tokens")
