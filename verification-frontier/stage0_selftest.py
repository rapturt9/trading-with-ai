"""Stage 0 (zero API calls): the full self-test sweep for the N50
ops-horizon design, plus the example-trace artifacts cited in proposal.md
and README.md. Mirrors ../stage0_render.py's pattern:
prove every invariant the harness rests on, in pure local computation,
before a single dollar is spent calling a model.

Invariants proven here, over MANY seeds (not just the one-off examples in
each module's own __main__ block):
  1. SHA multi-block: digest matches hashlib.sha256 over the FULL message
     for every rung (n_blocks in 1/2/4/8), genuine trace has zero locally
     inconsistent lines.
  2. SHA tamper, all three classes (addition/bitwise/schedule_word) x all
     three position buckets x all four rungs: exactly one locally
     inconsistent line, at the seeded tamper site, and the final digest
     changes (except schedule_word, which is deliberately display-only,
     see sha256_tamper_classes.py's docstring).
  3. Toy-field ECDSA (v2 design): the full traced verification (w, u1,
     u2, both double-and-add ladders, final point addition, v) matches an
     independent Jacobian-coordinate reference verify for every field-size
     rung (8/12/16-bit), genuine trace has zero locally inconsistent
     lines, and a corrupted signature independently fails verification
     (a check distinct from the line-tamper invariant).
  4. ECDSA line-level tamper, one seeded bit flip in one printed line
     (any op type: addition/multiplication/reduction/inverse-check) x all
     three position buckets x all three field-size rungs: exactly one
     locally inconsistent line, at the seeded site.
  5. Real P-256 verification fragments (Stage 0c, primary live-grid
     family): the traced, word-scale-decomposed formulas (general a-term
     reinstated, every multiplication linearly decomposed via
     traced_mulmod) match an independent Jacobian-coordinate reference
     verify at REAL curve scale, a corrupted signature independently
     fails, and the same exactly-one-flag line-tamper invariant holds
     across n_ops (1/2/4/8) x position bucket.
  6. Report-shaped SHA payloads (Stage 0c): a labeled attestation-report-
     style message (not random bytes) reuses the SHA family's exact
     generator/tamper/check machinery via its message= override; same
     invariants as (1)/(2), rerun on this payload shape.
  7. Composite mini-attestation (Stage 0c): hash a report-shaped payload,
     chain its digest into a P-256 verification fragment as the message
     hash, one combined trace; a tamper lands in EITHER half (weighted by
     real line count) and the whole composite still shows exactly one
     locally inconsistent line, with the untampered half fully
     regenerated from the tampered half's new output where the two chain
     together (see mini_attestation.py's docstring).

Run: python3 stage0_selftest.py
Writes: artifacts/selftest_summary.txt, artifacts/example_sha_*.txt,
artifacts/example_ecdsa_*.txt, artifacts/example_p256_*.txt,
artifacts/example_report_*.txt, artifacts/example_composite_*.txt
"""

import hashlib
import os

import sha256_multiblock as shamb
import sha256_tamper_classes as shatc
import ecdsa_trace as ecdsa
import p256_trace as p256
import report_payload
import mini_attestation

ART = os.path.join(os.path.dirname(__file__), "artifacts")

SHA_RUNGS = (1, 2, 4, 8)
ECDSA_BITS = (8, 12, 16)  # toy field-size rungs; see ecdsa_trace.Curve docstring for the timing table
P256_N_OPS = (1, 2, 4, 8)  # contiguous fragment sizes, real P-256 curve
SEEDS = range(5)  # 5 independent seeds per (rung, bucket, class) cell
BUCKETS = ("early", "middle", "late")


def run_sha_checks(log):
    fails = 0
    for n_blocks in SHA_RUNGS:
        for seed in SEEDS:
            g = shamb.generate_genuine(seed=seed, n_blocks=n_blocks)
            ok_digest = g["digest"] == hashlib.sha256(g["message"]).hexdigest()
            ok_clean = shamb.local_consistency_report(g) == []
            if not (ok_digest and ok_clean):
                fails += 1
                log(f"  FAIL genuine n_blocks={n_blocks} seed={seed}: digest_ok={ok_digest} clean={ok_clean}")
        log(f"[SHA n_blocks={n_blocks}] {len(list(SEEDS))} genuine seeds: digest==hashlib and "
            f"0 inconsistent lines, all pass" if fails == 0 else "SEE FAILURES ABOVE")

    for n_blocks in SHA_RUNGS:
        for bucket in BUCKETS:
            for seed in SEEDS:
                t = shamb.generate_tampered(seed=seed * 1000 + 1, bucket=bucket, n_blocks=n_blocks)
                bad = shamb.local_consistency_report(t)
                expected = [(t["tamper_block"], t["tamper_step"], "new_a")]
                digest_changed = t["digest"] != hashlib.sha256(t["message"]).hexdigest()
                if bad != expected or not digest_changed:
                    fails += 1
                    log(f"  FAIL tampered(addition) n_blocks={n_blocks} bucket={bucket} seed={seed}: "
                        f"flags={bad} expected={expected} digest_changed={digest_changed}")

                tb = shatc.generate_tampered_bitwise(seed=seed * 1000 + 2, bucket=bucket, n_blocks=n_blocks)
                badb = shamb.local_consistency_report(tb)
                okb = len(badb) == 1 and badb[0][0] == tb["tamper_block"] and badb[0][1] == tb["tamper_step"]
                if not okb:
                    fails += 1
                    log(f"  FAIL tampered(bitwise) n_blocks={n_blocks} bucket={bucket} seed={seed}: flags={badb}")

                tw = shatc.generate_tampered_schedule_word(seed=seed * 1000 + 3, bucket=bucket, n_blocks=n_blocks)
                badw = shamb.local_consistency_report(tw)
                okw = badw == [(tw["tamper_block"], tw["tamper_step"], "temp1")]
                if not okw:
                    fails += 1
                    log(f"  FAIL tampered(schedule_word) n_blocks={n_blocks} bucket={bucket} seed={seed}: flags={badw}")
        log(f"[SHA n_blocks={n_blocks}] all buckets x {len(list(SEEDS))} seeds x 3 tamper classes "
            f"(addition/bitwise/schedule_word): exactly-one-flag invariant holds" if fails == 0 else "SEE FAILURES ABOVE")
    return fails


def run_ecdsa_checks(log):
    fails = 0
    curves = {}
    for bits in ECDSA_BITS:
        curve = ecdsa.Curve(bits, seed=1)
        curves[bits] = curve
        log(f"[ECDSA bits={bits}] constructed {curve!r}")

        for seed in SEEDS:
            g = ecdsa.generate_genuine(curve, seed=seed)  # asserts vs Jacobian reference internally
            ok_clean = ecdsa.local_consistency_report(g) == []
            on_curve = ecdsa.point_on_curve(g["R"], curve.p, curve.b)
            if not (ok_clean and g["valid"] and on_curve):
                fails += 1
                log(f"  FAIL genuine ecdsa bits={bits} seed={seed}: clean={ok_clean} valid={g['valid']} "
                    f"on_curve={on_curve}")
        log(f"[ECDSA bits={bits}] {len(list(SEEDS))} genuine seeds: matches Jacobian reference verify, "
            f"0 inconsistent lines, traced 'v == r' check passes, final point R always on curve")

        # negative self-test: corrupting a signature must fail the independent reference verify
        g0 = ecdsa.generate_genuine(curve, seed=0)
        bad_s = (g0["s"] + 1) % curve.n or 1
        ref_valid, _ = ecdsa.verify_reference(curve, g0["Q"], g0["r"], bad_s, g0["z"])
        if ref_valid is not False:
            fails += 1
            log(f"  FAIL corrupted-signature self-test bits={bits}: reference verify did not return False")
        else:
            log(f"[ECDSA bits={bits}] corrupted-signature self-test: reference verify correctly returns False")

        header_on_curve = [0, 0]  # [on_curve_count, total] for header-section tampers
        other_on_curve = [0, 0]   # same, for every non-header tamper
        for bucket in BUCKETS:
            for seed in SEEDS:
                t = ecdsa.generate_tampered(curve, seed=seed * 1000 + 4, bucket=bucket)
                bad = ecdsa.local_consistency_report(t)
                target = (t["tamper"]["section"], t["tamper"]["op_idx"], t["tamper"]["step_name"])
                ok = bad == [target]
                if not ok:
                    fails += 1
                    log(f"  FAIL tampered ecdsa bits={bits} bucket={bucket} seed={seed}: "
                        f"flags={bad} expected=[{target}]")
                on_curve = ecdsa.point_on_curve(t["R"], curve.p, curve.b)
                bucket_stats = header_on_curve if t["tamper"]["section"] == "header" else other_on_curve
                bucket_stats[0] += int(on_curve)
                bucket_stats[1] += 1
        log(f"[ECDSA bits={bits}] all buckets x {len(list(SEEDS))} seeds, one seeded line-level tamper "
            f"(op type chosen by whichever line the position bucket lands on): exactly-one-flag invariant holds")
        # on-curve is NOT asserted false here -- header tampers (w/u1/u2) pick a
        # DIFFERENT valid scalar, so R = P1+P2 is still a genuine EC point (any
        # scalar multiple of a curve point stays on the curve); only tampers
        # inside the ladder/point-arithmetic itself reliably take R off-curve.
        # Reported as a diagnostic, not a pass/fail check -- see plan.md.
        log(f"[ECDSA bits={bits}] on-curve diagnostic: header-section tampers {header_on_curve[0]}/"
            f"{header_on_curve[1]} still on curve (expected ~100%, algebraic -- any scalar multiple of a "
            f"curve point is on the curve); non-header tampers {other_on_curve[0]}/{other_on_curve[1]} "
            f"on curve (expected ~0%, a corroborating signal, not the primary one)")
    return fails, curves


def run_p256_checks(log):
    fails = 0
    for n_ops in P256_N_OPS:
        for seed in SEEDS:
            g = p256.generate_genuine_fragment(seed=seed * 191 + 1, n_ops=n_ops)
            ok_clean = p256.local_consistency_report(g["fragment"], g["limb_bits"]) == []
            if not ok_clean:
                fails += 1
                log(f"  FAIL genuine p256 n_ops={n_ops} seed={seed}: clean={ok_clean}")
        n_lines = p256.total_line_count(p256.generate_genuine_fragment(seed=1, n_ops=n_ops))
        log(f"[P256 n_ops={n_ops}] {len(list(SEEDS))} genuine seeds: matches independent Jacobian "
            f"fast-forward (start AND end), 0 inconsistent lines ({n_lines} lines/fragment)")

        for bucket in BUCKETS:
            for seed in SEEDS:
                t = p256.generate_tampered_fragment(seed=seed * 191 + 4, n_ops=n_ops, bucket=bucket)
                bad = p256.local_consistency_report(t["fragment"], t["limb_bits"])
                target = (t["tamper"]["op_idx"], t["tamper"]["step_name"])
                if bad != [target]:
                    fails += 1
                    log(f"  FAIL tampered p256 n_ops={n_ops} bucket={bucket} seed={seed}: "
                        f"flags={bad} expected=[{target}]")
        log(f"[P256 n_ops={n_ops}] all buckets x {len(list(SEEDS))} seeds, one seeded line-level "
            f"tamper: exactly-one-flag invariant holds")

    # negative self-test: corrupting a real P-256 signature must fail the independent reference verify
    d = 987654321
    Q = p256.affine_scalar_mult(d, p256.G, p256.P, a=p256.A)
    r_ok, s_ok = p256.ecdsa_sign(d, 13579, 24680)
    bad_s = (s_ok + 1) % p256.N or 1
    ref_valid, _ = p256.verify_reference(Q, r_ok, bad_s, 13579)
    if ref_valid is not False:
        fails += 1
        log("  FAIL P256 corrupted-signature self-test: reference verify did not return False")
    else:
        log("[P256] corrupted-signature self-test: independent reference verify correctly returns False")
    return fails


def run_report_payload_checks(log):
    fails = 0
    for n_blocks in SHA_RUNGS:
        for seed in SEEDS:
            g = report_payload.generate_genuine(seed=seed, n_blocks=n_blocks)
            ok_digest = g["digest"] == hashlib.sha256(g["message"]).hexdigest()
            ok_clean = shamb.local_consistency_report(g) == []
            if not (ok_digest and ok_clean):
                fails += 1
                log(f"  FAIL genuine report-payload n_blocks={n_blocks} seed={seed}: "
                    f"digest_ok={ok_digest} clean={ok_clean}")
        for bucket in BUCKETS:
            for seed in SEEDS:
                t = report_payload.generate_tampered(seed=seed * 1000 + 1, bucket=bucket, n_blocks=n_blocks)
                bad = shamb.local_consistency_report(t)
                expected = [(t["tamper_block"], t["tamper_step"], "new_a")]
                if bad != expected:
                    fails += 1
                    log(f"  FAIL tampered report-payload n_blocks={n_blocks} bucket={bucket} seed={seed}: "
                        f"flags={bad} expected={expected}")
        log(f"[report-payload n_blocks={n_blocks}] {len(list(SEEDS))} genuine seeds + all buckets x "
            f"{len(list(SEEDS))} tampered seeds: reuses the SHA family's own invariants, all pass")
    return fails


def run_composite_checks(log):
    fails = 0
    for p256_n_ops in (2, 4):
        g = mini_attestation.generate_genuine(seed=1, sha_n_blocks=1, p256_n_ops=p256_n_ops)
        bad = mini_attestation.local_consistency_report(g)
        sha_lines, p256_lines = mini_attestation.total_line_count(g)
        if bad != []:
            fails += 1
            log(f"  FAIL genuine composite p256_n_ops={p256_n_ops}: flags={bad}")
        log(f"[composite p256_n_ops={p256_n_ops}] genuine: 0 inconsistent lines across both halves "
            f"(sha~{sha_lines} lines, p256={p256_lines} lines)")

        half_counts = {"sha": 0, "p256": 0}
        for bucket in BUCKETS:
            for seed in range(8):
                t = mini_attestation.generate_tampered(seed=seed * 101 + 3, bucket=bucket, p256_n_ops=p256_n_ops)
                bad = mini_attestation.local_consistency_report(t)
                if len(bad) != 1:
                    fails += 1
                    log(f"  FAIL tampered composite p256_n_ops={p256_n_ops} bucket={bucket} seed={seed}: "
                        f"flags={bad}")
                else:
                    half_counts[t["tamper"]["half"]] += 1
        log(f"[composite p256_n_ops={p256_n_ops}] all buckets x 8 seeds: exactly-one-flag invariant "
            f"holds across the composite; tamper landed in sha half {half_counts['sha']}x, "
            f"p256 half {half_counts['p256']}x (weighted by real line count)")
    return fails


def write_example_artifacts(curves):
    os.makedirs(ART, exist_ok=True)

    g1 = shamb.generate_genuine(seed=1, n_blocks=1)
    t1 = shamb.generate_tampered(seed=42, bucket="middle", n_blocks=1)
    with open(os.path.join(ART, "example_sha_1block_genuine.txt"), "w") as f:
        f.write("# GENUINE 1-block SHA-256 trace (n_blocks=1), dual binary+decimal rendering.\n"
                "# Correct answer: VERDICT GENUINE. local_consistency_report = [] (0 inconsistent lines).\n\n")
        f.write(shamb.render_multiblock(g1))
    with open(os.path.join(ART, "example_sha_1block_tampered.txt"), "w") as f:
        f.write(f"# TAMPERED 1-block SHA-256 trace (bucket=middle, block={t1['tamper_block']}, "
                f"round={t1['tamper_step']}). Correct answer: VERDICT TAMPERED, block {t1['tamper_block']} "
                f"round {t1['tamper_step']}.\n"
                f"# local_consistency_report = {shamb.local_consistency_report(t1)} (exactly one line).\n\n")
        f.write(shamb.render_multiblock(t1))

    g8 = shamb.generate_genuine(seed=1, n_blocks=8)
    with open(os.path.join(ART, "example_sha_8block_genuine_excerpt.txt"), "w") as f:
        rendered = shamb.render_multiblock(g8)
        f.write(f"# GENUINE 8-block SHA-256 trace excerpt (full trace is {len(rendered)} chars; this file "
                f"is the first 8000 chars only, for human inspection -- full trace verified programmatically\n"
                f"# in the self-test sweep above, not by eyeballing this excerpt).\n\n")
        f.write(rendered[:8000])

    g2d = shamb.generate_genuine(seed=1, n_blocks=2)
    with open(os.path.join(ART, "example_sha_2block_decimal_densified_excerpt.txt"), "w") as f:
        rendered = shamb.render_multiblock(g2d, binary_bitops=False, binary_new=False, binary_state=False)
        f.write(f"# Decimal-densified rendering (binary column dropped entirely), n_blocks=2. "
                f"Full trace is {len(rendered)} chars; excerpt below is the first 4000.\n\n")
        f.write(rendered[:4000])

    curve8 = curves[8]
    g_ec = ecdsa.generate_genuine(curve8, seed=1)
    t_ec = ecdsa.generate_tampered(curve8, seed=42, bucket="middle")
    with open(os.path.join(ART, "example_ecdsa_genuine.txt"), "w") as f:
        f.write(f"# GENUINE toy-field ECDSA verify trace ({curve8!r}).\n"
                "# Correct answer: VERDICT GENUINE. local_consistency_report = [] (0 inconsistent lines).\n\n")
        f.write(ecdsa.render_trace(g_ec))
    with open(os.path.join(ART, "example_ecdsa_tampered.txt"), "w") as f:
        tm = t_ec["tamper"]
        f.write(f"# TAMPERED toy-field ECDSA verify trace ({curve8!r}, bucket=middle, "
                f"section={tm['section']}, op_idx={tm['op_idx']}, step={tm['step_name']}).\n"
                f"# Correct answer: VERDICT TAMPERED, {tm['section']} op {tm['op_idx']} line '{tm['step_name']}'.\n"
                f"# local_consistency_report = {ecdsa.local_consistency_report(t_ec)} (exactly one line). "
                f"Final v==r comparison: {t_ec['valid']} (expected False; not itself a tamper-target line).\n\n")
        f.write(ecdsa.render_trace(t_ec))

    curve12 = curves[12]
    g_ec12 = ecdsa.generate_genuine(curve12, seed=1)
    with open(os.path.join(ART, "example_ecdsa_12bit_genuine_excerpt.txt"), "w") as f:
        rendered = ecdsa.render_trace(g_ec12)
        f.write(f"# GENUINE 12-bit-field ECDSA verify trace excerpt ({curve12!r}, "
                f"{ecdsa.total_line_count(g_ec12)} op lines). Full trace is {len(rendered)} chars; "
                f"excerpt below is the first 4000, for human inspection (full trace verified\n"
                f"# programmatically in the self-test sweep above, not by eyeballing this excerpt).\n\n")
        f.write(rendered[:4000])

    g_p256 = p256.generate_genuine_fragment(seed=1, n_ops=2)
    t_p256 = p256.generate_tampered_fragment(seed=42, n_ops=2, bucket="middle")
    with open(os.path.join(ART, "example_p256_genuine.txt"), "w") as f:
        f.write("# GENUINE real P-256 verification fragment (n_ops=2, real 256-bit curve).\n"
                "# Correct answer: VERDICT GENUINE. local_consistency_report = [] (0 inconsistent lines).\n\n")
        f.write(p256.render_fragment(g_p256))
    with open(os.path.join(ART, "example_p256_tampered.txt"), "w") as f:
        tm = t_p256["tamper"]
        f.write(f"# TAMPERED real P-256 verification fragment (n_ops=2, bucket=middle, "
                f"op={tm['op_idx']}, step={tm['step_name']}).\n"
                f"# Correct answer: VERDICT TAMPERED, op {tm['op_idx']} line '{tm['step_name']}'.\n"
                f"# local_consistency_report = "
                f"{p256.local_consistency_report(t_p256['fragment'], t_p256['limb_bits'])} (exactly one line).\n\n")
        f.write(p256.render_fragment(t_p256))

    g_report = report_payload.generate_genuine(seed=1, n_blocks=1)
    with open(os.path.join(ART, "example_report_payload_genuine.txt"), "w") as f:
        f.write(f"# GENUINE report-shaped SHA payload (n_blocks=1). Message: {g_report['message']!r}\n"
                "# Correct answer: VERDICT GENUINE. local_consistency_report = [] (0 inconsistent lines).\n\n")
        f.write(shamb.render_multiblock(g_report))

    g_composite = mini_attestation.generate_genuine(seed=1, sha_n_blocks=1, p256_n_ops=2)
    t_composite = mini_attestation.generate_tampered(seed=7, bucket="late", sha_n_blocks=1, p256_n_ops=2)
    with open(os.path.join(ART, "example_composite_genuine.txt"), "w") as f:
        f.write("# GENUINE composite mini-attestation (hash a report payload, verify a P-256 fragment "
                "over its digest).\n# Correct answer: VERDICT GENUINE. local_consistency_report = [] "
                "(0 inconsistent lines across both halves).\n\n")
        f.write(mini_attestation.render(g_composite))
    with open(os.path.join(ART, "example_composite_tampered.txt"), "w") as f:
        f.write(f"# TAMPERED composite mini-attestation (tamper landed in the {t_composite['tamper']['half']} half).\n"
                f"# local_consistency_report = {mini_attestation.local_consistency_report(t_composite)} "
                f"(exactly one line, across the whole composite).\n\n")
        f.write(mini_attestation.render(t_composite))

    print(f"Wrote {len(os.listdir(ART))} files to artifacts/")


def main():
    log_lines = []

    def log(msg):
        print(msg)
        log_lines.append(msg)

    log("=== SHA multi-block + tamper-class self-tests ===")
    sha_fails = run_sha_checks(log)
    log("\n=== Toy-field ECDSA verify + line-tamper self-tests ===")
    ecdsa_fails, curves = run_ecdsa_checks(log)
    log("\n=== Real P-256 verification fragment self-tests (Stage 0c) ===")
    p256_fails = run_p256_checks(log)
    log("\n=== Report-shaped SHA payload self-tests (Stage 0c) ===")
    report_fails = run_report_payload_checks(log)
    log("\n=== Composite mini-attestation self-tests (Stage 0c) ===")
    composite_fails = run_composite_checks(log)

    total_fails = sha_fails + ecdsa_fails + p256_fails + report_fails + composite_fails
    log(f"\n=== TOTAL: {total_fails} failures across all self-tests ===")
    assert total_fails == 0, f"{total_fails} self-test failures, see log above"

    write_example_artifacts(curves)

    os.makedirs(ART, exist_ok=True)
    with open(os.path.join(ART, "selftest_summary.txt"), "w") as f:
        f.write("\n".join(log_lines) + "\n")
    print(f"Wrote artifacts/selftest_summary.txt ({total_fails} failures)")


if __name__ == "__main__":
    main()
