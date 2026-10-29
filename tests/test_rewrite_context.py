from app import rewrite, context, grounding as gr

PROF_HI = {"languages": [("hi", 0.9), ("en", 0.1)], "scripts": {"DEVANAGARI": 0.9, "LATIN": 0.1}}


def test_script_first_prompt_orders_the_steps():
    s = rewrite.rewrite_system(["Hindi"])
    assert s.index("Language:") < s.index("Native:") < s.index("English:") < s.index("Hindi:")


def test_parse_plain_and_decorated_replies():
    raw = "Language: Hindi (romanized)\nNative: युद्ध कहाँ हुआ था?\nEnglish: Where did the war take place?"
    r = rewrite.parse(raw, "yudha kaha hua tha ?")
    assert r["native"].startswith("युद्ध") and r["english"] == "Where did the war take place?"
    deco = "1. **Language**: Hindi\n2. **Native**: \"युद्ध कहाँ हुआ था?\"\n3. **English**: \"Where did the war take place?\""
    r = rewrite.parse(deco, "x")
    assert r["language"] == "Hindi" and r["english"] == "Where did the war take place?"


def test_parse_rejects_a_wrong_english_line_and_echoes():
    r = rewrite.parse("English: युद्ध कहाँ हुआ था?\nNative: 12345", "q")
    assert r["english"] is None and r["native"] is None


def test_rewrite_queries_order_and_fallbacks():
    def gen(system, user, max_tokens=None):
        return ("Language: Hindi (romanized)\nNative: युद्ध कहाँ हुआ था?\n"
                "English: Where did the war take place?\nHindi: युद्ध कहाँ हुआ था?")
    q = rewrite.rewrite_queries("yudha kaha hua tha ?", PROF_HI, gen)
    assert q == ["Where did the war take place?", "युद्ध कहाँ हुआ था?"]
    assert rewrite.rewrite_queries("hello there", PROF_HI, lambda *a, **k: "") == []
    def boom(*a, **k): raise RuntimeError("down")
    assert rewrite.rewrite_queries("x y", PROF_HI, boom) == []


def _passage(n, sents):
    return {"n": n, "chunk_id": f"c{n}", "text": " ".join(sents)}


def test_compress_keeps_the_relevant_sentences_and_renumbers():
    filler = [f"Unrelated filler sentence number {i} about nothing in particular." for i in range(25)]
    p1 = _passage(1, filler[:12] + ["The battle was fought at Kurukshetra, the field of the Kurus."] + filler[12:])
    p2 = _passage(2, filler)
    out = context.compress([p1, p2], ["Where did the battle take place? Kurukshetra"], 150)
    assert 1 <= len(out) <= 2 and [e["n"] for e in out] == list(range(1, len(out) + 1))
    assert "Kurukshetra" in out[0]["text"] and out[0]["orig_n"] == 1
    assert gr.estimate_tokens(" ".join(e["text"] for e in out)) < 250


def test_compress_leaves_small_evidence_alone():
    ev = [_passage(1, ["Short passage here for the test."])]
    assert context.compress(ev, ["anything"], 1000) is ev


def test_compress_works_in_hindi():
    hi = [" ".join(f"यह वाक्य संख्या {i} है और इसमें कुछ खास नहीं है।" for i in range(30))
          + " युद्ध कुरुक्षेत्र के मैदान में हुआ था।"]
    out = context.compress([{"n": 1, "chunk_id": "c", "text": hi[0]}], ["युद्ध कहाँ हुआ था"], 120)
    assert "कुरुक्षेत्र" in out[0]["text"]


def test_adaptive_budget_learns_the_machine_speed():
    context._speed["tps"] = None
    assert context.adaptive_budget(5000) == 5000            # nothing known yet
    context.observe(2000, 80)                               # slow CPU: 25 tokens/s
    assert context.adaptive_budget(5000, 30) == 750
    context._speed["tps"] = None
    context.observe(2000, 4)                                # fast GPU: 500 tokens/s
    assert context.adaptive_budget(5000, 30) == 5000
    context.observe(100, 1)                                 # too small to learn from
    assert context.adaptive_budget(5000, 30) == 5000
