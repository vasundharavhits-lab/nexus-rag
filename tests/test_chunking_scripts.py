# the same chunking rules for every script
from app.chunking import chunk_structure, chunk_fixed, build_chunks
from app import grounding as gr


def sec(text):
    return {"heading_path": "A", "page": 1, "text": text}


def test_chinese_without_spaces_is_split():
    text = "".join(f"第{i}句话讲的是一件很普通的事情，没有什么特别的内容。" for i in range(120))
    chunks = chunk_structure([sec(text)], max_words=100, overlap=10)
    assert len(chunks) >= 5
    assert all(gr.units(c["text"]) <= 100 for c in chunks)
    assert "".join(c["text"] for c in chunks).count("第") >= 100          # nothing lost


def test_hindi_is_cut_at_the_danda_not_in_the_middle():
    text = " ".join(f"यह वाक्य संख्या {i} का पूरा अर्थ बताता है और अलग रखा गया है।" for i in range(80))
    chunks = chunk_structure([sec(text)], max_words=60, overlap=10)
    assert len(chunks) >= 5
    assert all(c["text"].rstrip().endswith("।") for c in chunks)


def test_english_behaviour_is_unchanged():
    text = " ".join(f"w{i}" for i in range(500))
    chunks = chunk_structure([sec(text)], max_words=100, overlap=20)
    a, b = chunks[0]["text"].split(), chunks[1]["text"].split()
    assert a[-20:] == b[:20] and all(len(c["text"].split()) <= 100 for c in chunks)


def test_fixed_strategy_and_word_count_for_unspaced_text():
    chunks = chunk_fixed([sec("字" * 1000)], max_words=100, overlap=10)
    assert len(chunks) >= 5
    rows = build_chunks("v1", [sec("字" * 1000)], "fixed")
    assert rows[0]["word_count"] >= 90
