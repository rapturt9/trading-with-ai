"""Stage 0 (zero API calls): token counts per rung, both task families,
both renderings, using tiktoken (same cl100k_base estimate the parent
the root package uses for its dry runs -- see sha256_trace.py
--dry-run). Reports which of the 5 live-run models' context windows each
rung fits, using the published/estimated context-window figures in
proposal.md's "Context windows" table.

Run: python3 token_dry_run.py
"""

import tiktoken

import sha256_multiblock as shamb
import ecdsa_trace as ecdsa
import p256_trace as p256
import report_payload
import mini_attestation

ENC = tiktoken.get_encoding("cl100k_base")

# Usable input context window in tokens, per model. gpt-4o and o3 are
# published figures; gpt-5's is the published 400k total context minus a
# 128k output reservation (272k usable input), the same convention used for
# the other reasoning models here. gpt-5.5 and claude-opus-4.6 have no
# separately published context window as of this design's writing -- the
# figures below are ASSUMED from their model family (gpt-5.5 assumed same
# as the gpt-5 family; claude-opus-4.6 assumed the Claude-family standard
# 200k) and flagged as such; proposal.md states this and the live-run stage
# should confirm both against the provider's model page before relying on
# them for a rung-selection decision.
CONTEXT_WINDOWS = {
    "openai/gpt-4o": (128_000, "published"),
    "openai/o3": (200_000, "published"),
    "openai/gpt-5": (272_000, "published (400k total - 128k output reservation)"),
    "openai/gpt-5.5": (272_000, "ASSUMED, same as gpt-5 family, not confirmed"),
    "anthropic/claude-opus-4.6": (200_000, "ASSUMED, Claude-family standard, not confirmed"),
}

SHA_RUNGS = (1, 2, 4, 8, 16, 32)
ECDSA_BITS = (8, 12, 16)  # small field-size rungs, see ecdsa_trace.Curve
P256_N_OPS = (1, 2, 4, 8)  # real-curve contiguous fragment sizes, see p256_trace.py


def toks(text):
    return len(ENC.encode(text))


def fits(n_tokens, headroom=0.7):
    """Which models fit n_tokens of trace within headroom * context_window
    (headroom leaves room for the prompt wrapper + the model's own CoT +
    answer, matching the ~50k-token single-block trace using well under a
    128k window in the parent project)."""
    return [m for m, (w, _) in CONTEXT_WINDOWS.items() if n_tokens <= headroom * w]


def main():
    print("=== SHA multi-block, dual (binary+decimal) rendering ===")
    rows = []
    for n_blocks in SHA_RUNGS:
        g = shamb.generate_genuine(seed=1, n_blocks=n_blocks)
        rendered = shamb.render_multiblock(g)
        n = toks(rendered)
        fitting = fits(n)
        rows.append((f"SHA dual n_blocks={n_blocks}", n, fitting))
        print(f"  n_blocks={n_blocks:3d} ({n_blocks * 448:5d} ops): {n:7d} tokens, "
              f"fits: {', '.join(m.split('/')[-1] for m in fitting) or 'NONE'}")

    print("\n=== SHA multi-block, decimal-densified rendering (binary column dropped) ===")
    for n_blocks in SHA_RUNGS:
        g = shamb.generate_genuine(seed=1, n_blocks=n_blocks)
        rendered = shamb.render_multiblock(g, binary_bitops=False, binary_new=False, binary_state=False)
        n = toks(rendered)
        fitting = fits(n)
        rows.append((f"SHA decimal-densified n_blocks={n_blocks}", n, fitting))
        print(f"  n_blocks={n_blocks:3d} ({n_blocks * 448:5d} ops): {n:7d} tokens, "
              f"fits: {', '.join(m.split('/')[-1] for m in fitting) or 'NONE'}")

    print("\n=== Small-curve ECDSA verify, decimal rendering ===")
    for bits in ECDSA_BITS:
        curve = ecdsa.Curve(bits, seed=1)
        g = ecdsa.generate_genuine(curve, seed=1)
        rendered = ecdsa.render_trace(g)
        n = toks(rendered)
        n_ops = ecdsa.total_line_count(g)
        fitting = fits(n)
        rows.append((f"ECDSA bits={bits} ({n_ops} ops, {curve!r})", n, fitting))
        print(f"  bits={bits:3d} ({n_ops:4d} ops, {curve!r}): {n:7d} tokens, "
              f"fits: {', '.join(m.split('/')[-1] for m in fitting) or 'NONE'}")

    print("\n=== Real P-256 verification fragments (Stage 0c, PRIMARY live-grid family) ===")
    for n_ops in P256_N_OPS:
        g = p256.generate_genuine_fragment(seed=1, n_ops=n_ops)
        rendered = p256.render_fragment(g)
        n = toks(rendered)
        n_lines = p256.total_line_count(g)
        fitting = fits(n)
        rows.append((f"P256 n_ops={n_ops} ({n_lines} lines)", n, fitting))
        print(f"  n_ops={n_ops:2d} ({n_lines:5d} lines): {n:7d} tokens, "
              f"fits: {', '.join(m.split('/')[-1] for m in fitting) or 'NONE'}")

    print("\n=== Report-shaped SHA payloads (Stage 0c) ===")
    for n_blocks in SHA_RUNGS[:4]:  # 1/2/4/8, the live-grid rungs; 16/32 not needed for a payload demo
        g = report_payload.generate_genuine(seed=1, n_blocks=n_blocks)
        rendered = shamb.render_multiblock(g)
        n = toks(rendered)
        fitting = fits(n)
        rows.append((f"report-payload n_blocks={n_blocks}", n, fitting))
        print(f"  n_blocks={n_blocks:2d} ({n_blocks * 448:5d} ops): {n:7d} tokens, "
              f"fits: {', '.join(m.split('/')[-1] for m in fitting) or 'NONE'}")

    print("\n=== Composite mini-attestation (Stage 0c) ===")
    for p256_n_ops in (1, 2, 4, 8):
        g = mini_attestation.generate_genuine(seed=1, sha_n_blocks=1, p256_n_ops=p256_n_ops)
        rendered = mini_attestation.render(g)
        n = toks(rendered)
        sha_lines, p256_lines = mini_attestation.total_line_count(g)
        fitting = fits(n)
        rows.append((f"composite sha1block+p256_n_ops={p256_n_ops}", n, fitting))
        print(f"  sha_n_blocks=1 + p256_n_ops={p256_n_ops:2d} (sha~{sha_lines}+p256={p256_lines} lines): "
              f"{n:7d} tokens, fits: {', '.join(m.split('/')[-1] for m in fitting) or 'NONE'}")

    print("\n=== Context windows used above ===")
    for m, (w, note) in CONTEXT_WINDOWS.items():
        print(f"  {m}: {w:,} tokens ({note})")

    print(f"\n=== Fit-in-context summary table (rung fits if trace <= 70% of context window) ===")
    header = ["rung", "tokens"] + [m.split("/")[-1] for m in CONTEXT_WINDOWS]
    print("  " + " | ".join(header))
    for label, n, fitting in rows:
        cells = ["YES" if m in fitting else "no" for m in CONTEXT_WINDOWS]
        print(f"  {label:45s} {n:7d} " + " | ".join(f"{c:>10s}" for c in cells))


if __name__ == "__main__":
    main()
