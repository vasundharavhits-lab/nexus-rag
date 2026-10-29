# tests/test_grounding.py - the helpers behave the same for every script
from app import grounding as gr

EN = "The Eastwick Health Clinic opened in 1987. It is managed by Asha Verma. The budget is 120,000 dollars."
HI = "आत्मा को शस्त्र काट नहीं सकते। इसे आग जला नहीं सकती। जल इसे गीला नहीं कर सकता।"
ZH = "东风诊所于1987年开业。它由王芳管理。年度预算为十二万美元。"
AR = "افتتحت العيادة في عام 1987. تديرها ليلى. الميزانية مئة ألف دولار."


def test_sentences_split_in_every_script():
    assert len(gr.split_sentences(EN)) == 3
    assert len(gr.split_sentences(HI)) == 3          # danda
    assert len(gr.split_sentences(ZH)) == 3          # CJK full stop, no spaces
    assert len(gr.split_sentences(AR)) == 3
    assert gr.split_sentences("Version 2.5 is out. See page 3.") == ["Version 2.5 is out.", "See page 3."]


def test_token_estimate_is_larger_for_dense_scripts():
    a = gr.estimate_tokens("a" * 100)
    assert gr.estimate_tokens("अ" * 100) > 2 * a
    assert gr.estimate_tokens("中" * 100) > 3 * a


def test_units_for_unspaced_text():
    assert gr.units("one two three") == 3
    assert gr.units("中" * 200) == 100


def test_cut_to_tokens_keeps_sentence_end():
    text = " ".join(f"Sentence number {i} is here." for i in range(50))
    cut = gr.cut_to_tokens(text, 60)
    assert cut.endswith(".") and gr.estimate_tokens(cut) <= 60


def test_evidence_budget_is_by_tokens_not_language():
    en = [{"n": i, "text": "word " * 150} for i in range(1, 7)]
    hi = [{"n": i, "text": "शब्द " * 150} for i in range(1, 7)]
    assert len(gr.select_evidence(en, 6, 3000)) > len(gr.select_evidence(hi, 6, 3000)) >= 1
    one = gr.select_evidence([{"n": 1, "text": "x " * 20000}], 4, 2000)
    assert len(one) == 1 and gr.estimate_tokens(one[0]["text"]) <= 1100


def test_tidy_moves_leading_citation_and_drops_repeats():
    assert gr.tidy("[1] The clinic opened in 1987.") == "The clinic opened in 1987. [1]"
    assert gr.tidy("It opened in 1987. [1] It opened in 1987. [1]") == "It opened in 1987. [1]"
    assert gr.tidy("Fine answer here. [1]") == "Fine answer here. [1]"
    assert gr.tidy("First sentence is complete. [1] Second sentence is cut of") == "First sentence is complete. [1]"
    assert gr.tidy("Answer. (source id=2)") == "Answer. [2]"


def test_poor_answers_are_recognised_by_shape():
    assert gr.is_poor("[2]") and gr.is_poor("ok [1]")
    assert gr.is_poor("go go go go go go go go go go go go go go go")
    assert not gr.is_poor("The clinic is managed by Asha Verma. [1]")
    assert not gr.is_poor("诊所由王芳管理。[1]")          # unspaced script, still a real answer
    assert not gr.is_poor("क्लिनिक का प्रबंधन आशा करती हैं। [1]")


EVID = [
    {"n": 1, "text": EN},
    {"n": 2, "text": "The fire station keeps four engines ready. The depot houses 80 vehicles."},
]


def test_extractive_picks_the_matching_sentence_english():
    r = gr.extractive_answer(["Who manages the Eastwick Health Clinic?"], EVID)
    assert r["n"] == 1 and "It is managed by Asha Verma." in r["sentences"]


def test_extractive_hindi_and_chinese():
    r = gr.extractive_answer(["आग से क्या होता है इसे जला"], [{"n": 3, "text": HI}])
    assert r and "आग" in r["sentences"][0]
    r = gr.extractive_answer(["年度预算是多少"], [{"n": 4, "text": ZH}])
    assert r and "预算" in r["sentences"][0]


def test_extractive_returns_nothing_for_unrelated_question():
    assert gr.extractive_answer(["quantum chromodynamics lattice"], EVID) is None


def test_extractive_with_embedder_and_render():
    def eq(q): return [1.0, 0.0]
    def et(ts): return [[1.0, 0.0] if "managed" in t else [0.0, 1.0] for t in ts]
    r = gr.extractive_answer(["who runs it"], EVID, embed_query=eq, embed_texts=et)
    assert r["n"] == 1 and "managed" in r["sentences"][0]
    assert gr.render_extractive(r).endswith("[1]")


def test_localize_caches_and_falls_back():
    calls = []
    def gen(system, user, max_tokens=None):
        calls.append(1); return "Message en français"
    gr._loc_cache.clear()
    a = gr.localize("I could not find an answer.", "Quelle heure est-il ?", "fr", gen)
    b = gr.localize("I could not find an answer.", "Autre question ?", "fr", gen)
    assert a == b == "Message en français" and len(calls) == 1
    def boom(*a, **k): raise RuntimeError("down")
    assert gr.localize("I could not find an answer.", "x", None, boom) == "I could not find an answer."
