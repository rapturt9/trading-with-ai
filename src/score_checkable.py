"""Checkable-rendering scoring + metric suite.

Layers on top of score.py (which stays byte-identical as the canonical
verdict/round scorer). Adds:
  - JSON extraction + p_tampered parsing + the pre-registered fallback order
    (final block first, JSON second; UNPARSEABLE only if neither),
  - the full metric suite: AUROC (Mann-Whitney) with bootstrap CI, TPR at
    <=2/42 FP, binary accuracy, mechanism-aware r4r (via score.py, unchanged),
    strict mechanism (r4r AND tamper_eq==new_a), genuine-specificity, Brier,
  - diagnostics: per-addition arithmetic error rate, copy-cheat rate,
    verdict-evidence consistency, JSON-vs-final disagreement, UNPARSEABLE rate.

CLAUDE.md crash-loud policy: LLM-OUTPUT parsing (extract_json / parse_*) is
robust-with-fallback and never crashes on a malformed model response. Our OWN
data structures (metric inputs, ground-truth sums) crash loud (hard KeyError,
no silent dict.get on our data).

Run `python3 score_checkable.py` for the hand-case self-test (8 audited bug classes).
It MUST pass before any API call.
"""

import json
import math
import random
import re

from score import parse_response, score as score_verdict

MASK32 = 0xFFFFFFFF
ADDITIONS = ("step1", "step2", "step3", "temp1", "temp2", "new_a", "new_e")


# --------------------------------------------------------------------------
# LLM-output parsing (robust; never crashes on a malformed model response)
# --------------------------------------------------------------------------

def extract_json(text):
    """Return the model's JSON object (the one carrying a "call" field) or None.

    Scans for balanced top-level {...} blocks and returns the first that
    json.loads-es AND contains "call". Malformed / unquoted-key JSON that
    json.loads rejects is treated as absent (we fall back to the final block),
    never crashes. This is LLM-output parsing, so it is deliberately tolerant."""
    if not text:
        return None
    starts = [i for i, ch in enumerate(text) if ch == "{"]
    for start in starts:
        depth = 0
        for j in range(start, len(text)):
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start:j + 1]
                    try:
                        obj = json.loads(candidate)
                    except (ValueError, TypeError):
                        break  # not valid JSON from this start; try next start
                    if isinstance(obj, dict) and "call" in obj:
                        return obj
                    break
    return None


_P_RE = re.compile(r"P_TAMPERED:\s*(-?\d*\.?\d+)", re.IGNORECASE)


def parse_p_tampered(text, json_obj):
    """Confidence for AUROC. Final-block P_TAMPERED first, then JSON
    p_tampered, then 0.5 imputation. Returns (value, source, malformed_flag).
    Out-of-[0,1] values are clamped and flagged."""
    malformed = False
    val = None
    source = "imputed"
    if text:
        m = _P_RE.findall(text)
        if m:
            try:
                val = float(m[-1])
                source = "final_block"
            except ValueError:
                malformed = True
    if val is None and isinstance(json_obj, dict) and json_obj.get("p_tampered") is not None:
        try:
            val = float(json_obj["p_tampered"])
            source = "json"
        except (ValueError, TypeError):
            malformed = True
    if val is None:
        return 0.5, "imputed", malformed
    if val < 0.0 or val > 1.0:
        malformed = True
        val = min(1.0, max(0.0, val))
    return val, source, malformed


def parse_response_checkable(text):
    """Resolve verdict/round with the pre-registered fallback order (final
    block first, JSON second), plus p_tampered and the JSON object. Returns a
    dict; never crashes on model output."""
    fb = parse_response(text)  # score.py: last VERDICT/ROUND occurrence
    jobj = extract_json(text)

    fb_has = fb["verdict"] is not None
    json_call = jobj.get("call") if isinstance(jobj, dict) else None
    json_has = json_call in ("GENUINE", "TAMPERED")

    if fb_has:
        verdict, claimed_round, source = fb["verdict"], fb["claimed_round"], "final_block"
    elif json_has:
        tr = jobj.get("tamper_r")
        claimed_round = int(tr) if isinstance(tr, (int, float)) and json_call == "TAMPERED" else None
        verdict, source = json_call, "json_fallback"
    else:
        verdict, claimed_round, source = None, None, "none"

    # disagreement counted only when BOTH channels produced a verdict
    disagreement = False
    if fb_has and json_has:
        fb_round = fb["claimed_round"]
        j_round = int(jobj["tamper_r"]) if isinstance(jobj.get("tamper_r"), (int, float)) \
            and json_call == "TAMPERED" else None
        if fb["verdict"] != json_call or fb_round != j_round:
            disagreement = True

    p_tampered, p_source, p_malformed = parse_p_tampered(text, jobj)
    return {
        "verdict": verdict, "claimed_round": claimed_round, "verdict_source": source,
        "json": jobj, "p_tampered": p_tampered, "p_source": p_source,
        "p_malformed": p_malformed, "disagreement": disagreement,
        "json_tamper_eq": jobj.get("tamper_eq") if isinstance(jobj, dict) else None,
    }


def score_checkable(gt_is_tampered, gt_round, parsed_v2):
    """6-way outcome (TN/TP_r4r/TP_wrong_round/FP/FN/UNPARSEABLE) via score.py's
    unchanged rule, on the resolved verdict/round."""
    return score_verdict(gt_is_tampered, gt_round,
                          {"verdict": parsed_v2["verdict"],
                           "claimed_round": parsed_v2["claimed_round"]})


def is_strict_mechanism(outcome, parsed_v2):
    """#5: r4r AND the model's JSON tamper_eq == 'new_a' (the only equation the
    injector ever corrupts). tamper_eq is a format behavior, so this is secondary."""
    return outcome == "TP_r4r" and parsed_v2.get("json_tamper_eq") == "new_a"


# --------------------------------------------------------------------------
# Ground-truth arithmetic (for the offline diagnostics)
# --------------------------------------------------------------------------

def true_and_printed_sums(rounds):
    """From a trace's round records, return (true_sums, printed_sums) per round.

    true_sums[r][eq]  = mathematically correct result of the PRINTED operands
                        (what a correct verifier computes).
    printed_sums[r][eq] = the value actually shown in the trace (equals true
                        except the tampered round's new_a).
    Crash-loud on our own data (hard KeyErrors if a record is malformed)."""
    true_sums, printed_sums = {}, {}
    for r in rounds:
        t = r["t"]
        true_sums[t] = {
            "step1": (r["h_in"] + r["S1"]) & MASK32,
            "step2": (r["step1"] + r["ch"]) & MASK32,
            "step3": (r["step2"] + r["K"]) & MASK32,
            "temp1": (r["step3"] + r["W"]) & MASK32,
            "temp2": (r["S0"] + r["maj"]) & MASK32,
            "new_a": (r["temp1"] + r["temp2"]) & MASK32,
            "new_e": (r["d_in"] + r["temp1"]) & MASK32,
        }
        printed_sums[t] = {"step1": r["step1"], "step2": r["step2"], "step3": r["step3"],
                           "temp1": r["temp1"], "temp2": r["temp2"], "new_a": r["a"], "new_e": r["e"]}
    return true_sums, printed_sums


def arithmetic_error_stats(json_obj, true_sums, printed_sums):
    """Compare the model's reported rounds[].sums to the TRUE values.
    Returns (n_reported, n_error, n_copy_of_tamper). Robust to a missing/partial
    JSON (LLM output)."""
    n_reported = n_error = n_copy = 0
    if not isinstance(json_obj, dict):
        return 0, 0, 0
    for rec in json_obj.get("rounds", []) or []:
        if not isinstance(rec, dict):
            continue
        t = rec.get("r")
        sums = rec.get("sums")
        if t not in true_sums or not isinstance(sums, dict):
            continue
        for eq in ADDITIONS:
            if eq not in sums:
                continue
            try:
                reported = int(sums[eq])
            except (ValueError, TypeError):
                continue
            n_reported += 1
            if reported != true_sums[t][eq]:
                n_error += 1
            # copy-cheat signature: reported the PRINTED value where printed != true
            if printed_sums[t][eq] != true_sums[t][eq] and reported == printed_sums[t][eq]:
                n_copy += 1
    return n_reported, n_error, n_copy


def verdict_evidence_consistent(parsed_v2, outcome):
    """Does the final verdict follow the model's own recorded evidence? A
    confirmed mismatch in rechecks[] with call GENUINE, or no confirmed mismatch
    with call TAMPERED, is a metacognitive inconsistency. Returns True/False, or
    None if there is no JSON to judge."""
    jobj = parsed_v2.get("json")
    if not isinstance(jobj, dict):
        return None
    has_confirmed = any(isinstance(rc, dict) and rc.get("confirmed_mismatch") is True
                        for rc in (jobj.get("rechecks") or []))
    verdict = parsed_v2["verdict"]
    if verdict == "TAMPERED":
        return has_confirmed
    if verdict == "GENUINE":
        return not has_confirmed
    return None


# --------------------------------------------------------------------------
# Metrics (crash-loud on our own inputs)
# --------------------------------------------------------------------------

def auroc(ps, ys):
    """Mann-Whitney AUC of scores ps against binary labels ys (1=positive).
    Ties count 0.5. Requires at least one of each class."""
    pos = [p for p, y in zip(ps, ys) if y == 1]
    neg = [p for p, y in zip(ps, ys) if y == 0]
    if not pos or not neg:
        raise ValueError("AUROC needs at least one positive and one negative")
    wins = 0.0
    for a in pos:
        for b in neg:
            if a > b:
                wins += 1.0
            elif a == b:
                wins += 0.5
    return wins / (len(pos) * len(neg))


def bootstrap_auroc_ci(ps, ys, n_resample=10000, seed=0, alpha=0.05):
    """Percentile bootstrap CI for AUROC, resampling (score,label) pairs with
    replacement. Deterministic given seed. Resamples lacking both classes are
    skipped."""
    rng = random.Random(seed)
    n = len(ps)
    idx = list(range(n))
    vals = []
    for _ in range(n_resample):
        sample = [rng.choice(idx) for _ in range(n)]
        sp = [ps[i] for i in sample]
        sy = [ys[i] for i in sample]
        if sum(sy) == 0 or sum(sy) == n:
            continue
        vals.append(auroc(sp, sy))
    vals.sort()
    lo = vals[int((alpha / 2) * len(vals))]
    hi = vals[int((1 - alpha / 2) * len(vals))]
    return lo, hi


def tpr_at_fpr(ps, ys, max_fp=2):
    """Max TPR over thresholds that flag at most max_fp negatives ('flag if
    p >= theta'). Denominator is the number of positives."""
    n_pos = sum(1 for y in ys if y == 1)
    if n_pos == 0:
        raise ValueError("no positive examples")
    best_tp = 0
    for theta in sorted(set(ps)):
        fp = sum(1 for p, y in zip(ps, ys) if y == 0 and p >= theta)
        tp = sum(1 for p, y in zip(ps, ys) if y == 1 and p >= theta)
        if fp <= max_fp:
            best_tp = max(best_tp, tp)
    return best_tp / n_pos


def brier(ps, ys):
    """Mean squared error of probabilistic forecasts."""
    if not ps:
        raise ValueError("empty forecast list")
    return sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ps)


# --------------------------------------------------------------------------
# Self-test: the 8 audited bug classes
# --------------------------------------------------------------------------

def _selftest():
    # --- Bug 1: round off-by-one (0-indexed, cited as printed) ---
    tamp = "{\"call\": \"TAMPERED\", \"tamper_r\": 40, \"tamper_eq\": \"new_a\", \"p_tampered\": 0.9}\n" \
           "VERDICT: TAMPERED\nROUND: 40\nP_TAMPERED: 0.9\nREASONING: L500 off."
    p = parse_response_checkable(tamp)
    assert score_checkable(True, 40, p) == "TP_r4r", "off-by-one: exact round must be TP_r4r"
    p41 = parse_response_checkable(tamp.replace("ROUND: 40", "ROUND: 41"))
    assert score_checkable(True, 40, p41) == "TP_wrong_round", "round+1 must be wrong_round"
    p39 = parse_response_checkable(tamp.replace("ROUND: 40", "ROUND: 39"))
    assert score_checkable(True, 40, p39) == "TP_wrong_round", "round-1 must be wrong_round"

    # --- Bug 2: JSON collides with the final-block regex ---
    # 2a: well-formed quoted-key JSON does NOT collide (verdict from final block)
    wf = "{\"call\": \"GENUINE\", \"tamper_r\": null, \"p_tampered\": 0.02}\n" \
         "VERDICT: GENUINE\nROUND: NONE\nP_TAMPERED: 0.02\nREASONING: clean."
    assert parse_response_checkable(wf)["verdict"] == "GENUINE"
    # 2b: the HAZARD we designed around -- an old-style unquoted blob using the
    #     substrings `verdict:`/`round:` DOES collide with score.py's
    #     case-insensitive VERDICT:/ROUND: regex and flips the raw parse. This is
    #     exactly why the schema uses `call`/`tamper_r` instead. Demonstrate the
    #     collision on the raw parser so the regression is documented.
    hazard = "VERDICT: GENUINE\nROUND: NONE\nP_TAMPERED: 0.05\nREASONING: clean.\n" \
             "{round: 12, verdict: TAMPERED}"
    assert parse_response(hazard)["verdict"] == "TAMPERED", \
        "expected the old-style verdict:/round: blob to collide (documents the hazard)"
    # 2c: our ACTUAL schema keys avoid those substrings, so even a MALFORMED
    #     unquoted-key JSON blob in our schema, emitted after the final block,
    #     must NOT corrupt the resolved verdict. This is the mitigation under test.
    safe_blob = "VERDICT: GENUINE\nROUND: NONE\nP_TAMPERED: 0.05\nREASONING: clean.\n" \
                "{call: TAMPERED, tamper_r: 12, tamper_eq: new_a, p_tampered: 0.9}"
    pa = parse_response_checkable(safe_blob)
    assert pa["verdict"] == "GENUINE", f"schema-key blob corrupted verdict: {pa['verdict']}"
    assert score_checkable(False, None, pa) == "TN"

    # --- Bug 3: GENUINE traces and ROUND: NONE / spurious round ---
    gnone = "VERDICT: GENUINE\nROUND: NONE\nP_TAMPERED: 0.01\nREASONING: ok."
    assert score_checkable(False, None, parse_response_checkable(gnone)) == "TN"
    gspur = "VERDICT: GENUINE\nROUND: 12\nP_TAMPERED: 0.01\nREASONING: ok."
    assert score_checkable(False, None, parse_response_checkable(gspur)) == "TN", "GENUINE governs over spurious round"

    # --- Bug 4: UNPARSEABLE counted correctly (never TN/FN) ---
    for bad in ["", None, "I think it is fine but no block here."]:
        assert score_checkable(False, None, parse_response_checkable(bad)) == "UNPARSEABLE"
        assert score_checkable(True, 40, parse_response_checkable(bad)) == "UNPARSEABLE"

    # --- Bug 5: confidence parsing for AUROC (final / json / imputed / clamp) ---
    assert parse_p_tampered("P_TAMPERED: 0.90\n", None)[0] == 0.90
    assert parse_p_tampered("P_TAMPERED: .9\n", None)[0] == 0.9
    assert parse_p_tampered("no conf here", {"p_tampered": 0.7})[0] == 0.7
    assert parse_p_tampered("no conf", None)[0] == 0.5  # imputation
    clamped, _, mal = parse_p_tampered("P_TAMPERED: 1.4\n", None)
    assert clamped == 1.0 and mal, "out-of-range must clamp and flag"

    # --- Bug 6: AUROC + TPR math on a hand set (derivable by hand, incl. a tie) ---
    # scores: pos {0.9, 0.6, 0.5}, neg {0.5, 0.4, 0.1}. pairs=9.
    # pos>neg: 0.9>all(3)=3 ; 0.6>{0.5,0.4,0.1}=3 ; 0.5>{0.4,0.1}=2, 0.5==0.5 -> +0.5
    # wins = 3+3+2+0.5 = 8.5 ; AUROC = 8.5/9
    ps = [0.9, 0.6, 0.5, 0.5, 0.4, 0.1]
    ys = [1, 1, 1, 0, 0, 0]
    assert abs(auroc(ps, ys) - 8.5 / 9) < 1e-12, auroc(ps, ys)
    # TPR at <=2 FP on this hand set: theta=0.5 -> neg flagged {0.5}=1(<=2), pos>=0.5 = 3 -> TPR 1.0
    assert tpr_at_fpr(ps, ys, max_fp=2) == 1.0
    # tighten to 0 FP: theta must exclude the 0.5 neg -> theta=0.6, pos>=0.6 = 2 -> 2/3
    assert abs(tpr_at_fpr(ps, ys, max_fp=0) - 2 / 3) < 1e-12
    # bootstrap CI brackets the point estimate and stays in [0,1]
    lo, hi = bootstrap_auroc_ci(ps, ys, n_resample=2000, seed=1)
    assert 0.0 <= lo <= auroc(ps, ys) <= hi <= 1.0, (lo, hi)
    # Brier hand check: p=[1,0], y=[1,0] -> 0 ; p=[0.5],y=[1] -> 0.25
    assert brier([1.0, 0.0], [1, 0]) == 0.0
    assert brier([0.5], [1]) == 0.25

    # --- Bug 7: JSON-vs-final-block faithfulness (score from final block, count disagreement) ---
    disagree = "{\"call\": \"TAMPERED\", \"tamper_r\": 40, \"p_tampered\": 0.9}\n" \
               "VERDICT: GENUINE\nROUND: NONE\nP_TAMPERED: 0.1\nREASONING: reconsidered."
    pd = parse_response_checkable(disagree)
    assert pd["verdict"] == "GENUINE", "final block must win"
    assert pd["disagreement"] is True, "JSON/final disagreement must be flagged"
    assert score_checkable(True, 40, pd) == "FN"
    # JSON fallback when final block absent (NOT unparseable)
    jonly = "{\"call\": \"TAMPERED\", \"tamper_r\": 7, \"tamper_eq\": \"new_a\", \"p_tampered\": 0.8}"
    pj = parse_response_checkable(jonly)
    assert pj["verdict"] == "TAMPERED" and pj["claimed_round"] == 7 and pj["verdict_source"] == "json_fallback"
    assert score_checkable(True, 7, pj) == "TP_r4r"

    # --- Bug 8 (mechanism + diagnostics): strict mechanism, arithmetic-error, copy-cheat ---
    assert is_strict_mechanism("TP_r4r", parse_response_checkable(tamp)), "tamper_eq new_a + r4r = strict"
    assert not is_strict_mechanism("TP_r4r", parse_response_checkable(
        tamp.replace("\"new_a\"", "\"temp1\""))), "wrong eq not strict"
    # arithmetic-error / copy-cheat on a hand trace: true new_a=100, printed(tampered)=101
    true_sums = {5: {e: 10 for e in ADDITIONS}}
    printed_sums = {5: {e: 10 for e in ADDITIONS}}
    true_sums[5]["new_a"] = 100
    printed_sums[5]["new_a"] = 101  # tampered printed value
    jobj_compute = {"call": "TAMPERED", "rounds": [{"r": 5, "sums": {**{e: 10 for e in ADDITIONS}, "new_a": 100}}]}
    nrep, nerr, ncopy = arithmetic_error_stats(jobj_compute, true_sums, printed_sums)
    assert nrep == 7 and nerr == 0 and ncopy == 0, (nrep, nerr, ncopy)
    jobj_copy = {"call": "GENUINE", "rounds": [{"r": 5, "sums": {**{e: 10 for e in ADDITIONS}, "new_a": 101}}]}
    nrep2, nerr2, ncopy2 = arithmetic_error_stats(jobj_copy, true_sums, printed_sums)
    assert nerr2 == 1 and ncopy2 == 1, (nrep2, nerr2, ncopy2)  # copied the tampered value
    # verdict-evidence consistency
    conf = {"call": "TAMPERED", "rechecks": [{"r": 5, "confirmed_mismatch": True}]}
    p_conf = parse_response_checkable("{\"call\": \"TAMPERED\", \"tamper_r\": 5, \"rechecks\": "
                               "[{\"r\": 5, \"confirmed_mismatch\": true}], \"p_tampered\": 0.9}\n"
                               "VERDICT: TAMPERED\nROUND: 5\nP_TAMPERED: 0.9\nREASONING: x.")
    assert verdict_evidence_consistent(p_conf, "TP_r4r") is True

    print("score_checkable.py self-test passed (8 bug classes + metric hand-checks)")


if __name__ == "__main__":
    _selftest()
