"""Stage 0 (zero API): regenerate the example rendered traces + prove the
local-consistency invariant that the whole Phase 3 design rests on.

Invariant: in the dual rendering, a GENUINE trace has ZERO locally inconsistent
equations, and a TAMPERED trace has EXACTLY ONE: the tampered round's `new_a`
(printed new_a != printed temp1 + printed temp2). Because render_dual prints
both bases from the same integer, this integer-level check certifies both-base
consistency at once. Verified across all 84 seeded traces, not just the examples.

Writes audit artifacts into review/artifacts/. Run: python3 src/render_examples.py
"""

import os

from run_experiment import build_dataset, build_prompt_v2
from sha256_trace import render_dual, local_consistency_report

ART = os.path.join(os.path.dirname(__file__), "..", "review", "artifacts")


def highlight_tamper(rendered, tamper_step):
    """Return the rendered trace with a >>> marker on the tampered round's
    `new a` line, for human inspection."""
    out = []
    in_round = False
    for line in rendered.split("\n"):
        # a round header looks like 'L####: round <t> (K[...'
        marker = f"round {tamper_step} ("
        if marker in line:
            in_round = True
        elif "round " in line and "(K[" in line:
            in_round = False
        if in_round and "new a =" in line:
            out.append(">>> TAMPERED LINE >>> " + line)
        else:
            out.append(line)
    return "\n".join(out)


def main():
    os.makedirs(ART, exist_ok=True)
    items = build_dataset()

    # --- full invariant sweep over all 84 traces ---
    genuine_bad = tampered_ok = tampered_bad = 0
    first_tampered_idx = None
    for idx, item in enumerate(items):
        bad = local_consistency_report(item["trace"])
        if item["kind"] == "genuine":
            if bad:
                genuine_bad += 1
                print(f"  FAIL: genuine idx={idx} has inconsistencies {bad}")
        else:
            ts = item["trace"]["tamper_step"]
            expected = [(ts, "new_a")]
            if bad == expected:
                tampered_ok += 1
                if first_tampered_idx is None:
                    first_tampered_idx = idx
            else:
                tampered_bad += 1
                print(f"  FAIL: tampered idx={idx} (step {ts}) inconsistencies = {bad} (expected {expected})")
    assert genuine_bad == 0, f"{genuine_bad} genuine traces had inconsistent lines"
    assert tampered_bad == 0, f"{tampered_bad} tampered traces did not have exactly [(step,new_a)]"
    print(f"INVARIANT HOLDS: 42/42 genuine have 0 inconsistent lines; "
          f"{tampered_ok}/42 tampered have EXACTLY the tampered round's new_a inconsistent.")

    # --- render the two example traces (genuine idx0, first tampered) ---
    g_item = items[0]
    t_item = items[first_tampered_idx]
    t_step = t_item["trace"]["tamper_step"]

    g_render = render_dual(g_item["trace"])
    t_render = render_dual(t_item["trace"])

    with open(os.path.join(ART, "example_genuine_dual.txt"), "w") as f:
        f.write(f"# GENUINE example (dataset idx 0, seed 1). Correct answer: VERDICT GENUINE.\n")
        f.write(f"# Rendered by render_dual(); local_consistency_report = [] (no inconsistent lines).\n\n")
        f.write(g_render)
    with open(os.path.join(ART, "example_tampered_dual.txt"), "w") as f:
        f.write(f"# TAMPERED example (dataset idx {first_tampered_idx}, tamper_step={t_step}, "
                f"bucket={t_item['trace']['bucket']}). Correct answer: VERDICT TAMPERED, ROUND {t_step}.\n")
        f.write(f"# The ONLY locally inconsistent line is round {t_step}'s `new a` "
                f"(printed new_a != printed temp1 + printed temp2); every other line, including all\n")
        f.write(f"# downstream rounds, checks out. local_consistency_report = "
                f"{local_consistency_report(t_item['trace'])}.\n\n")
        f.write(highlight_tamper(t_render, t_step))

    # A compact excerpt of the tampered round for the report / artifact index.
    t_lines = t_render.split("\n")
    excerpt = []
    for i, line in enumerate(t_lines):
        if f"round {t_step} (" in line:
            excerpt = t_lines[i:i + 20]
            break
    with open(os.path.join(ART, "example_tampered_round_excerpt.txt"), "w") as f:
        f.write(f"# Tampered round {t_step} (dataset idx {first_tampered_idx}); "
                f"the `new a` line is the single inconsistency.\n\n")
        f.write("\n".join(excerpt))

    print(f"Wrote review/artifacts/example_genuine_dual.txt, example_tampered_dual.txt "
          f"(idx {first_tampered_idx}, step {t_step}), example_tampered_round_excerpt.txt")

    # true printed sums check for the tampered round, so the excerpt is self-proving
    r = next(rr for rr in t_item["trace"]["rounds"] if rr["t"] == t_step)
    correct_new_a = (r["temp1"] + r["temp2"]) & 0xFFFFFFFF
    print(f"  round {t_step}: printed new_a = {r['a']}, but temp1+temp2 mod 2^32 = {correct_new_a} "
          f"(differ -> the tamper)")


if __name__ == "__main__":
    main()
