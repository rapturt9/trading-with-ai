"""One-off extraction script for artifacts/traces/*.txt (Deliverable 1 for
Ram: full raw model interactions, nothing paraphrased or trimmed).

Reads logs_pilot/*.eval directly via inspect_ai.log.read_eval_log (all 8
logs read cleanly with the currently-installed inspect_ai -- the extra_body
fix for reasoning_effort="max" mentioned in plan.md's pilot entry only
affects opus-4.6/fable-5 *raw-API* calls; these logs were all written by
this pilot's own harness, post-fix, and none needed the zipfile+json
fallback). Zero new API calls: this only reads already-collected logs.

Run: python3 extract_traces.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from inspect_ai.log import read_eval_log

LOGS_DIR = os.path.join(os.path.dirname(__file__), "logs_pilot")
OUT_DIR = os.path.join(os.path.dirname(__file__), "artifacts", "traces")

# (output_filename, log_filename, sample_index, one-line description)
CASES = [
    ("gpt5_TP_r4r_ecdsa231.txt",
     "2026-07-12T17-32-07+00-00_verification-frontier_Cg4xhDmme3cF6xy7YaN7yW.eval", 3,
     "gpt-5, small-curve ECDSA bits=8, tampered, correct verdict + exact location"),
    ("gpt5_FN_sha448.txt",
     "2026-07-12T17-24-09+00-00_verification-frontier_mtNjJTEWYYiNzzD9xgn7aS.eval", 2,
     "gpt-5, SHA n_blocks=1 (448 ops), tampered, missed (FN) -- the N=448 decay point"),
    ("gpt5_FN_sha896.txt",
     "2026-07-12T19-08-09+00-00_verification-frontier_eAeh2AnN4SFXjEKWiEUUTT.eval", 2,
     "gpt-5, SHA n_blocks=2 (896 ops), tampered, missed (FN) -- the N=896 decay point"),
    ("gpt5_TN_sha448.txt",
     "2026-07-12T17-24-09+00-00_verification-frontier_mtNjJTEWYYiNzzD9xgn7aS.eval", 0,
     "gpt-5, SHA n_blocks=1 (448 ops), genuine, correctly called clean (TN)"),
    ("opus46_TP_r4r_sha448.txt",
     "2026-07-12T17-35-43+00-00_verification-frontier_YkP4s2jTwqGFSZCCvzXi7h.eval", 2,
     "claude-opus-4.6, SHA n_blocks=1 (448 ops), tampered, correct verdict + exact location"),
    ("opus46_TP_r4r_sha896.txt",
     "2026-07-12T19-07-58+00-00_verification-frontier_iQ3kNd6qQct8HQZYhfvAjR.eval", 1,
     "claude-opus-4.6, SHA n_blocks=2 (896 ops), tampered, correct verdict + exact location -- opus remains unbounded above 896"),
    ("opus46_TN_sha448.txt",
     "2026-07-12T17-35-43+00-00_verification-frontier_YkP4s2jTwqGFSZCCvzXi7h.eval", 0,
     "claude-opus-4.6, SHA n_blocks=1 (448 ops), genuine, correctly called clean (TN)"),
    ("o3_TP_r4r_ecdsa231.txt",
     "2026-07-12T19-19-32+00-00_verification-frontier_CrWDekaMctfRrHpAHxfZRB.eval", 7,
     "o3, small-curve ECDSA bits=8 (231 ops, exact match), tampered, correct verdict + exact location"),
    ("gpt4o_FP_genuine_ecdsa231.txt",
     "2026-07-12T19-19-28+00-00_verification-frontier_VW9e5sVkMMpzZWeCKUK7cG.eval", 0,
     "gpt-4o, small-curve ECDSA bits=8 (231 ops, exact match), GENUINE trace, called TAMPERED (false positive) -- the miscalibration finding"),
    ("gpt4o_TP_wrongloc_ecdsa231.txt",
     "2026-07-12T19-19-28+00-00_verification-frontier_VW9e5sVkMMpzZWeCKUK7cG.eval", 7,
     "gpt-4o, small-curve ECDSA bits=8 (231 ops, exact match), tampered trace, called TAMPERED but named the wrong line -- the miscalibration finding, tampered side"),
]


def content_to_text(content):
    """A ChatMessage's .content is either a plain str, or a list of content
    blocks (ContentText / ContentReasoning / etc, from inspect_ai's Content
    union). Returns (reasoning_text_or_None, visible_text)."""
    if isinstance(content, str):
        return None, content
    reasoning_parts = []
    text_parts = []
    for block in content:
        btype = type(block).__name__
        if btype == "ContentReasoning":
            reasoning_parts.append(block.reasoning)
        elif btype == "ContentText":
            text_parts.append(block.text)
        else:
            text_parts.append(f"[[unhandled content block type: {btype}]]\n{block!r}")
    reasoning = "\n".join(reasoning_parts) if reasoning_parts else None
    text = "\n".join(text_parts)
    return reasoning, text


def render_case(out_name, log_fn, idx, desc):
    path = os.path.join(LOGS_DIR, log_fn)
    log = read_eval_log(path)
    s = log.samples[idx]
    sc = s.scores["r4r_frontier_scorer"]
    md = sc.metadata

    user_msg = next(m for m in s.messages if m.role == "user")
    asst_msg = next(m for m in s.messages if m.role == "assistant")
    _, prompt_text = content_to_text(user_msg.content)
    reasoning_text, visible_text = content_to_text(asst_msg.content)

    lines = []
    lines.append("=" * 100)
    lines.append(f"CASE: {desc}")
    lines.append("=" * 100)
    lines.append("")
    lines.append("--- PROVENANCE (verbatim from Score.metadata, logs_pilot/*.eval; nothing hand-entered) ---")
    lines.append(f"source .eval file : logs_pilot/{log_fn}")
    lines.append(f"sample index       : {idx}  (sample.id={s.id})")
    lines.append(f"model_key          : {md['model_key']}   (api_model={md['api_model']}, eci={md['eci']})")
    lines.append(f"family / rung      : {md['family']} / {md['rung']}")
    lines.append(f"n_ops (this trace) : {md['n_ops']}")
    lines.append(f"kind               : {md['kind']}   (genuine = no tamper injected; tampered = one seeded bit flip)")
    lines.append(f"tamper bucket/seed : bucket={md['bucket']} seed={md['seed']} op_type={md['op_type']}")
    lines.append(f"ground truth       : gt_is_tampered={md['gt_is_tampered']} gt_loc={md['gt_loc']}")
    lines.append(f"reasoning_effort   : {md['reasoning_effort']}   max_tokens={md['max_tokens']}")
    lines.append(f"rendering/variant  : rendering={md['rendering']} prompt_variant={md['prompt_variant']}")
    lines.append(f"git_commit         : {md['git_commit']}")
    lines.append(f"stop_reason        : {s.output.stop_reason}")
    if s.output.usage:
        u = s.output.usage
        lines.append(f"usage (this call)  : input_tokens={u.input_tokens} output_tokens={u.output_tokens} reasoning_tokens={u.reasoning_tokens}")
    lines.append("")
    lines.append("--- SCORED OUTCOME ---")
    lines.append(f"outcome            : {md['outcome']}")
    lines.append(f"parsed verdict     : {md['verdict']}   parsed loc: {md['loc']}")
    lines.append(f"verdict_source     : {md['verdict_source']}  (final_block = read from the model's final answer block, per the r4r scoring contract)")
    lines.append(f"p_tampered         : {md['p_tampered']}  (p_source={md['p_source']}, p_malformed={md['p_malformed']})")
    lines.append(f"disagreement       : {md['disagreement']}  (True if the JSON block and final-answer block disagreed; final block wins per score_frontier.py)")
    lines.append(f"score.value        : {sc.value}   score.answer: {sc.answer}")
    lines.append(f"score.explanation  : {sc.explanation}")
    lines.append("")
    lines.append("=" * 100)
    lines.append("FULL PROMPT AS SENT (complete user message, unmodified)")
    lines.append("=" * 100)
    lines.append(prompt_text)
    lines.append("")
    lines.append("=" * 100)
    if reasoning_text is not None:
        # OpenAI models (o3, gpt-5, gpt-5.5) via OpenRouter return an
        # ENCRYPTED reasoning item, not a plain-text summary: an opaque
        # Fernet-token-shaped blob (starts "gAAAAA", no whitespace, tens of
        # KB) that is not human-readable. Anthropic models (opus-4.6) return
        # real plain-text reasoning through the same code path. Detected
        # here (no space in the first 200 chars) rather than dumping ~40KB
        # of ciphertext as if it were inspectable prose.
        looks_encrypted = " " not in reasoning_text[:200] and len(reasoning_text) > 500
        if looks_encrypted:
            lines.append("MODEL REASONING CONTENT: returned, but ENCRYPTED (not human-readable)")
            lines.append("=" * 100)
            lines.append(
                "This model (OpenAI, via OpenRouter) returns its reasoning as an opaque\n"
                "encrypted blob -- a Fernet-token-shaped string (starts 'gAAAAA', no\n"
                f"whitespace anywhere, {len(reasoning_text):,} characters here) -- not a plain-text\n"
                "reasoning summary. This is OpenAI's encrypted-reasoning-item behavior\n"
                "(the item round-trips for multi-turn tool use but cannot be decoded by a\n"
                "third party), passed through unmodified by OpenRouter. usage.reasoning_tokens\n"
                f"for this call was {s.output.usage.reasoning_tokens if s.output.usage else 'unknown'} (billed, real reasoning happened) but the CONTENT is not\n"
                "inspectable from this log. Contrast with the opus-4.6 trace files in this\n"
                "same folder, where Anthropic returns real plain-text reasoning through the\n"
                "identical extraction code path -- so this is a provider behavior difference,\n"
                "not an extraction bug. First 300 characters of the encrypted blob, for\n"
                "provenance only (not decodable):"
            )
            lines.append(reasoning_text[:300] + " ...[truncated, encrypted, non-decodable]...")
        else:
            lines.append("FULL MODEL REASONING CONTENT (ContentReasoning block, as returned by the provider)")
            lines.append("=" * 100)
            lines.append(reasoning_text)
    else:
        lines.append("MODEL REASONING CONTENT: none returned by the provider for this call")
        lines.append("(gpt-4o on OpenRouter does not return a reasoning channel; usage.reasoning_tokens=0")
        lines.append(" confirms no hidden reasoning was billed either -- this is not a missing-capture bug.)")
        lines.append("=" * 100)
    lines.append("")
    lines.append("=" * 100)
    lines.append("FULL VISIBLE MODEL OUTPUT (ContentText / completion, complete, unmodified)")
    lines.append("=" * 100)
    lines.append(visible_text)
    lines.append("")

    out_path = os.path.join(OUT_DIR, out_name)
    with open(out_path, "w") as f:
        f.write("\n".join(lines))
    print(f"wrote {out_path}  ({os.path.getsize(out_path):,} bytes)")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for out_name, log_fn, idx, desc in CASES:
        render_case(out_name, log_fn, idx, desc)


if __name__ == "__main__":
    main()
