# app/context.py
"""Make the evidence fit the machine. A CPU-only computer reads a prompt at a few dozen tokens per second, so
four whole passages can cost a minute before the first word of the answer. Two language-agnostic steps:

  compress()         keep only the sentences of each passage that matter for the question (rare-word overlap +
                     embeddings, any script), plus the sentence that follows, within a token budget
  adaptive_budget()  learn how fast this machine reads prompts and choose the budget that keeps an answer
                     inside a target time. No hard-coded speed: a GPU gets a large budget, a laptop a small one.
"""
from app import grounding as gr

_speed = {"tps": None}


def observe(prompt_tokens, seconds, weight=0.4):
    """Record one generation: `prompt_tokens` estimated tokens read in `seconds` (includes writing the answer,
    so the speed is slightly under-estimated, which keeps the budget on the safe side)."""
    if prompt_tokens < 200 or seconds < 0.5:
        return
    tps = prompt_tokens / seconds
    _speed["tps"] = tps if _speed["tps"] is None else (1 - weight) * _speed["tps"] + weight * tps


def adaptive_budget(cap, target_seconds=30, floor=500):
    """Prompt tokens to send: `cap` until the machine's speed is known, then what fits in `target_seconds`."""
    tps = _speed["tps"]
    if tps is None or target_seconds <= 0:
        return cap
    return int(max(floor, min(cap, tps * target_seconds)))


def compress(evidence, queries, budget_tokens, embed_query=None, embed_texts=None):
    """Shrink the passages to `budget_tokens`. Passages that already fit come back unchanged. Passages keep
    their order and are renumbered 1..n (citations use these numbers); 'orig_n' keeps the old number."""
    total = sum(gr.estimate_tokens(e["text"]) for e in evidence)
    if total <= budget_tokens or not evidence:
        return evidence
    cands = []                                              # (passage n, sentence, position in passage)
    for e in evidence:
        for pos, s in enumerate(gr.split_sentences(e["text"])):
            if sum(c.isalnum() for c in s) >= 6:
                cands.append((e["n"], s, pos))
    if not cands:
        return evidence
    _, _, score = gr.score_sentences([(n, s) for n, s, _ in cands], queries, embed_query, embed_texts)
    order = sorted(range(len(cands)), key=score.__getitem__, reverse=True)
    index = {(n, pos): i for i, (n, _, pos) in enumerate(cands)}
    chosen, used = set(), 0

    def add(i):
        nonlocal used
        if i in chosen:
            return True
        cost = gr.estimate_tokens(cands[i][1]) + 2
        if used + cost > budget_tokens and chosen:
            return False
        chosen.add(i)
        used += cost
        return True

    for i in order:
        if used >= budget_tokens:
            break
        if not add(i):
            continue
        nxt = index.get((cands[i][0], cands[i][2] + 1))     # the sentence after a good one usually completes it
        if nxt is not None and score[nxt] > 0:
            add(nxt)
    out = []
    for e in evidence:
        keep = sorted(i for i in chosen if cands[i][0] == e["n"])
        if not keep:
            continue
        pieces, prev = [], None
        for i in keep:
            if prev is not None and cands[i][2] != prev + 1:
                pieces.append("\u2026")                      # a gap in the passage
            pieces.append(cands[i][1])
            prev = cands[i][2]
        out.append(dict(e, text=" ".join(pieces), orig_n=e["n"]))
    return [dict(e, n=i) for i, e in enumerate(out, 1)]
