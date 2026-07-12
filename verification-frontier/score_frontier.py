"""Scoring for the N50 ops-horizon Inspect harness (inspect_task_frontier.py).

Generalizes ../score_v2.py's right-for-right-reason (r4r) rule
to BOTH families here. rq3's rule requires naming the exact tampered ROUND;
this experiment's generators can tamper any of several fields/steps per round
(SHA: addition/bitwise/schedule_word classes) or any line in an ECDSA point-op
(header/ladder1/ladder2/final_add/v), so r4r here requires naming the exact
3-part location tuple that each family's own `local_consistency_report`
returns -- (block, round, field) for SHA, (section, op_idx, step_name) for
ECDSA -- not just a round number. Ground truth for every tampered sample is
taken directly from `local_consistency_report(trace)[0]` (asserted length 1
at dataset-build time), never re-derived by hand, so scoring can never drift
from what the generator itself proved is the one inconsistent line.

Per-family location schema (labels are both the JSON keys, with a
`tamper_`-prefix, and the final-answer-block line labels):

  sha:   BLOCK (int), ROUND (int), FIELD (str, e.g. new_a/S1/temp1)
  ecdsa: SECTION (str, header/ladder1/ladder2/final_add/v), OP_IDX (int),
         STEP (str, e.g. y3/lam/u1_raw)

CLAUDE.md crash-loud policy: parsing the MODEL's response is robust-with-
fallback and never crashes on malformed output (an LLM can emit anything).
Our OWN data (ground-truth tuples, ints/strs pulled straight off the trace)
crashes loud -- no dict.get, no silent fallback -- since a KeyError there
would be a real bug in the harness, not a model mistake.

Run `python3 score_frontier.py` for the self-test. It must pass before any
API call (Stage 0's own discipline, extended to this scoring layer).
"""

import json
import re

FAMILY_CONFIG = {
    "sha": {
        "labels": ("BLOCK", "ROUND", "FIELD"),
        "json_keys": ("tamper_block", "tamper_round", "tamper_field"),
        "types": (int, int, str),
    },
    "ecdsa": {
        "labels": ("SECTION", "OP_IDX", "STEP"),
        "json_keys": ("tamper_section", "tamper_op_idx", "tamper_step"),
        "types": (str, int, str),
    },
    "p256": {
        # 2-part, not 3: p256_trace.py's local_consistency_report returns
        # (op_idx, step_name) tuples -- a fragment has no "section" (it's a
        # single contiguous span of one ladder, not header/ladder1/ladder2/
        # final_add/v like the full toy-ECDSA verify).
        "labels": ("OP_IDX", "STEP"),
        "json_keys": ("tamper_op_idx", "tamper_step"),
        "types": (int, str),
    },
}

_VERDICT_RE = re.compile(r"VERDICT:\s*(GENUINE|TAMPERED)", re.IGNORECASE)
_P_RE = re.compile(r"P_TAMPERED:\s*(-?\d*\.?\d+)", re.IGNORECASE)


def _coerce(raw, typ):
    """Parse one final-block location value. 'NONE'/'null'/empty -> None.
    Never raises: an unparseable int field (model wrote "unknown" for BLOCK)
    becomes None, which just can't match any real ground-truth tuple -- the
    right behavior for LLM-output parsing, not a crash."""
    raw = raw.strip().rstrip(".")
    if raw == "" or raw.upper() in ("NONE", "NULL"):
        return None
    if typ is int:
        m = re.match(r"-?\d+", raw)
        return int(m.group()) if m else None
    return raw  # str: keep as-written (field/step names are exact tokens, e.g. "new_a")


def _last_label_value(text, label, typ):
    matches = re.findall(rf"^{label}:\s*(.*)$", text, re.IGNORECASE | re.MULTILINE)
    if not matches:
        return None
    return _coerce(matches[-1], typ)


def parse_final_block(text, family):
    """Last VERDICT: + last of each location label, matching score_v2's
    'take the LAST occurrence' convention (a model that restates its answer
    should be scored on its final statement)."""
    cfg = FAMILY_CONFIG[family]
    if not text:
        return None, (None, None, None)
    vm = _VERDICT_RE.findall(text)
    verdict = vm[-1].upper() if vm else None
    loc = tuple(_last_label_value(text, label, typ) for label, typ in zip(cfg["labels"], cfg["types"]))
    return verdict, loc


def extract_json(text, family):
    """Return the model's JSON object (must contain "call") or None. Same
    balanced-brace scan as score_v2.extract_json, generalized to any family
    (the scan itself doesn't depend on which keys the schema uses)."""
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
                        break
                    if isinstance(obj, dict) and "call" in obj:
                        return obj
                    break
    return None


def _json_loc(jobj, family):
    cfg = FAMILY_CONFIG[family]
    out = []
    for key, typ in zip(cfg["json_keys"], cfg["types"]):
        v = jobj.get(key)
        if v is None:
            out.append(None)
        elif typ is int:
            try:
                out.append(int(v))
            except (ValueError, TypeError):
                out.append(None)
        else:
            out.append(str(v))
    return tuple(out)


def parse_p_tampered(text, json_obj):
    """Identical convention to score_v2.parse_p_tampered: final block first,
    then JSON, then 0.5 imputation; out-of-range clamped and flagged."""
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


def parse_response_frontier(text, family):
    """Resolve verdict/location with the pre-registered fallback order (final
    block first, JSON second -- matching rq3-replication's v2 convention),
    plus p_tampered and the raw JSON object. Never crashes on model output."""
    if family not in FAMILY_CONFIG:
        raise ValueError(f"unknown family {family!r}")  # our own bug, crash loud

    fb_verdict, fb_loc = parse_final_block(text, family)
    jobj = extract_json(text, family)
    json_call = jobj.get("call") if isinstance(jobj, dict) else None
    json_has = json_call in ("GENUINE", "TAMPERED")

    fb_has = fb_verdict is not None
    if fb_has:
        verdict, loc, source = fb_verdict, fb_loc, "final_block"
    elif json_has:
        verdict, loc, source = json_call, _json_loc(jobj, family), "json_fallback"
    else:
        verdict, loc, source = None, (None, None, None), "none"

    disagreement = False
    if fb_has and json_has:
        j_loc = _json_loc(jobj, family)
        if fb_verdict != json_call or fb_loc != j_loc:
            disagreement = True

    p_tampered, p_source, p_malformed = parse_p_tampered(text, jobj)
    return {
        "verdict": verdict, "loc": loc, "verdict_source": source,
        "json": jobj, "p_tampered": p_tampered, "p_source": p_source,
        "p_malformed": p_malformed, "disagreement": disagreement,
    }


def score_frontier(gt_is_tampered, gt_loc, parsed):
    """6-way outcome, generalized from score.py/score_v2.py's rule to a
    3-part location tuple instead of a bare round number:
      TN            genuine, called GENUINE
      FP            genuine, called TAMPERED
      FN            tampered, called GENUINE
      TP_r4r        tampered, called TAMPERED, location EXACTLY matches
      TP_wrong_loc  tampered, called TAMPERED, location does not match
      UNPARSEABLE   no verdict recovered from either channel
    """
    verdict = parsed["verdict"]
    if verdict is None:
        return "UNPARSEABLE"
    if not gt_is_tampered:
        return "TN" if verdict == "GENUINE" else "FP"
    if verdict == "GENUINE":
        return "FN"
    # verdict == "TAMPERED"
    return "TP_r4r" if parsed["loc"] == gt_loc else "TP_wrong_loc"


# --------------------------------------------------------------------------
# Self-test
# --------------------------------------------------------------------------

def _selftest():
    # --- SHA family ---
    sha_tamp_text = (
        '{"call": "TAMPERED", "tamper_block": 1, "tamper_round": 40, '
        '"tamper_field": "new_a", "p_tampered": 0.92}\n'
        "VERDICT: TAMPERED\nBLOCK: 1\nROUND: 40\nFIELD: new_a\n"
        "P_TAMPERED: 0.92\nREASONING: L900 addition off by one bit."
    )
    p = parse_response_frontier(sha_tamp_text, "sha")
    assert p["verdict"] == "TAMPERED" and p["loc"] == (1, 40, "new_a")
    assert score_frontier(True, (1, 40, "new_a"), p) == "TP_r4r"
    assert score_frontier(True, (1, 41, "new_a"), p) == "TP_wrong_loc", "wrong round -> wrong_loc"
    assert score_frontier(True, (1, 40, "S1"), p) == "TP_wrong_loc", "wrong field -> wrong_loc"
    assert score_frontier(True, (0, 40, "new_a"), p) == "TP_wrong_loc", "wrong block -> wrong_loc"

    sha_genuine_text = "VERDICT: GENUINE\nBLOCK: NONE\nROUND: NONE\nFIELD: NONE\nP_TAMPERED: 0.02\nREASONING: clean."
    pg = parse_response_frontier(sha_genuine_text, "sha")
    assert pg["loc"] == (None, None, None)
    assert score_frontier(False, (None, None, None), pg) == "TN"
    assert score_frontier(False, (None, None, None), p) == "FP", "TAMPERED call on a genuine trace -> FP"

    # JSON-only fallback (no final block)
    sha_json_only = ('{"call": "TAMPERED", "tamper_block": 0, "tamper_round": 5, '
                      '"tamper_field": "S1", "p_tampered": 0.8}')
    pj = parse_response_frontier(sha_json_only, "sha")
    assert pj["verdict"] == "TAMPERED" and pj["loc"] == (0, 5, "S1") and pj["verdict_source"] == "json_fallback"
    assert score_frontier(True, (0, 5, "S1"), pj) == "TP_r4r"

    # disagreement: JSON says TAMPERED, final block (which wins) says GENUINE
    sha_disagree = ('{"call": "TAMPERED", "tamper_block": 0, "tamper_round": 5, '
                     '"tamper_field": "S1", "p_tampered": 0.8}\n'
                     "VERDICT: GENUINE\nBLOCK: NONE\nROUND: NONE\nFIELD: NONE\n"
                     "P_TAMPERED: 0.1\nREASONING: reconsidered.")
    pd = parse_response_frontier(sha_disagree, "sha")
    assert pd["verdict"] == "GENUINE" and pd["disagreement"] is True
    assert score_frontier(True, (0, 5, "S1"), pd) == "FN"

    # unparseable
    for bad in ["", None, "no structured answer here"]:
        pu = parse_response_frontier(bad, "sha")
        assert score_frontier(False, (None, None, None), pu) == "UNPARSEABLE"
        assert score_frontier(True, (1, 40, "new_a"), pu) == "UNPARSEABLE"

    # p_tampered parsing/clamping
    assert parse_p_tampered("P_TAMPERED: 0.90\n", None)[0] == 0.90
    assert parse_p_tampered("no conf here", {"p_tampered": 0.7})[0] == 0.7
    assert parse_p_tampered("no conf", None)[0] == 0.5
    clamped, _, mal = parse_p_tampered("P_TAMPERED: 1.4\n", None)
    assert clamped == 1.0 and mal

    # --- ECDSA family ---
    ec_tamp_text = (
        '{"call": "TAMPERED", "tamper_section": "ladder2", "tamper_op_idx": 2, '
        '"tamper_step": "y3", "p_tampered": 0.95}\n'
        "VERDICT: TAMPERED\nSECTION: ladder2\nOP_IDX: 2\nSTEP: y3\n"
        "P_TAMPERED: 0.95\nREASONING: L219 y3 off."
    )
    pe = parse_response_frontier(ec_tamp_text, "ecdsa")
    assert pe["loc"] == ("ladder2", 2, "y3")
    assert score_frontier(True, ("ladder2", 2, "y3"), pe) == "TP_r4r"
    assert score_frontier(True, ("ladder1", 2, "y3"), pe) == "TP_wrong_loc", "wrong section -> wrong_loc"
    assert score_frontier(True, ("ladder2", 3, "y3"), pe) == "TP_wrong_loc", "wrong op_idx -> wrong_loc"
    assert score_frontier(True, ("ladder2", 2, "x3"), pe) == "TP_wrong_loc", "wrong step -> wrong_loc"

    ec_genuine_text = "VERDICT: GENUINE\nSECTION: NONE\nOP_IDX: NONE\nSTEP: NONE\nP_TAMPERED: 0.03\nREASONING: clean."
    peg = parse_response_frontier(ec_genuine_text, "ecdsa")
    assert peg["loc"] == (None, None, None)
    assert score_frontier(False, (None, None, None), peg) == "TN"

    # header-section tamper (op_idx conventionally 0, not within a ladder)
    ec_header_text = (
        '{"call": "TAMPERED", "tamper_section": "header", "tamper_op_idx": 0, '
        '"tamper_step": "u1", "p_tampered": 0.7}\n'
        "VERDICT: TAMPERED\nSECTION: header\nOP_IDX: 0\nSTEP: u1\n"
        "P_TAMPERED: 0.7\nREASONING: u1 inconsistent with w*z."
    )
    ph = parse_response_frontier(ec_header_text, "ecdsa")
    assert score_frontier(True, ("header", 0, "u1"), ph) == "TP_r4r"

    for bad in ["", None]:
        pu = parse_response_frontier(bad, "ecdsa")
        assert score_frontier(True, ("ladder2", 2, "y3"), pu) == "UNPARSEABLE"

    # --- p256 family (2-part location: op_idx, step -- no section) ---
    p256_tamp_text = (
        '{"call": "TAMPERED", "tamper_op_idx": 3, "tamper_step": "lam", "p_tampered": 0.92}\n'
        "VERDICT: TAMPERED\nOP_IDX: 3\nSTEP: lam\nP_TAMPERED: 0.92\nREASONING: L512 lam off."
    )
    pp = parse_response_frontier(p256_tamp_text, "p256")
    assert pp["loc"] == (3, "lam")
    assert score_frontier(True, (3, "lam"), pp) == "TP_r4r"
    assert score_frontier(True, (4, "lam"), pp) == "TP_wrong_loc", "wrong op_idx -> wrong_loc"
    assert score_frontier(True, (3, "x3"), pp) == "TP_wrong_loc", "wrong step -> wrong_loc"

    p256_genuine_text = "VERDICT: GENUINE\nOP_IDX: NONE\nSTEP: NONE\nP_TAMPERED: 0.04\nREASONING: clean."
    ppg = parse_response_frontier(p256_genuine_text, "p256")
    assert ppg["loc"] == (None, None)
    assert score_frontier(False, (None, None), ppg) == "TN"

    print("score_frontier.py self-test passed (SHA + ECDSA + P-256 location scoring, fallback, disagreement, unparseable)")


if __name__ == "__main__":
    _selftest()
