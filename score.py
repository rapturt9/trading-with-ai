"""Scoring logic: parses a model's response against ground truth.

Right-for-right-reason (r4r) rule, matching chippy's own adjustment (which
materially changed several of their headline numbers): a TAMPERED verdict only
counts as a real detection if the model also names the correct round. A
TAMPERED verdict on the wrong round is scored as a miss, not a hit, since it
means the model didn't actually find the tamper, it guessed or pattern-matched.
"""

import re


def parse_response(text):
    """Takes the LAST VERDICT/ROUND occurrence, not the first: the prompt now
    invites full step-by-step reasoning before the final answer, so the model
    may reference hypothetical verdicts while thinking out loud. Only the
    final, requested three-line block is the actual answer."""
    if not text:
        # a reasoning model can exhaust its token budget on hidden reasoning
        # and return empty/None visible content; that's a real outcome (the
        # budget was too small for this prompt), not a parse bug, so it scores
        # as UNPARSEABLE rather than crashing.
        return {"verdict": None, "claimed_round": None, "raw": text}
    verdict_matches = re.findall(r"VERDICT:\s*(GENUINE|TAMPERED)", text, re.IGNORECASE)
    round_matches = re.findall(r"ROUND:\s*(NONE|\d+)", text, re.IGNORECASE)
    verdict = verdict_matches[-1].upper() if verdict_matches else None
    round_str = round_matches[-1].upper() if round_matches else None
    claimed_round = None if round_str in (None, "NONE") else int(round_str)
    return {"verdict": verdict, "claimed_round": claimed_round, "raw": text}


def score(ground_truth_is_tampered, ground_truth_round, parsed_response):
    """Returns one of: TN (correct genuine), TP_r4r (correct tampered, right
    round), TP_wrong_round (said tampered, wrong round, counts as a miss per
    r4r), FP (said tampered on a genuine trace), FN (said genuine on a
    tampered trace), UNPARSEABLE (response didn't match the expected format).
    """
    if parsed_response["verdict"] is None:
        return "UNPARSEABLE"

    said_tampered = parsed_response["verdict"] == "TAMPERED"

    if not ground_truth_is_tampered:
        return "FP" if said_tampered else "TN"

    # ground truth is tampered
    if not said_tampered:
        return "FN"
    if parsed_response["claimed_round"] == ground_truth_round:
        return "TP_r4r"
    return "TP_wrong_round"


if __name__ == "__main__":
    # local self-test of the parser and scoring rule only, no API involved
    genuine_reply = "VERDICT: GENUINE\nROUND: NONE\nREASONING: all rounds check out."
    tampered_correct_reply = "VERDICT: TAMPERED\nROUND: 40\nREASONING: round 40's temp1 is wrong."
    tampered_wrong_round_reply = "VERDICT: TAMPERED\nROUND: 12\nREASONING: something looks off around here."
    fp_reply = "VERDICT: TAMPERED\nROUND: 5\nREASONING: I think I see an issue."

    assert score(False, None, parse_response(genuine_reply)) == "TN"
    assert score(True, 40, parse_response(tampered_correct_reply)) == "TP_r4r"
    assert score(True, 40, parse_response(tampered_wrong_round_reply)) == "TP_wrong_round"
    assert score(False, None, parse_response(fp_reply)) == "FP"
    assert score(True, 40, parse_response(genuine_reply)) == "FN"
    print("score.py self-test passed")
