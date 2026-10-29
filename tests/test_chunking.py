from app.chunking import chunk_structure, chunk_fixed, build_chunks

def sec(path, text):
    return {"heading_path": path, "page": None, "text": text}

def test_long_paragraph_is_split_with_overlap():
    text = " ".join(f"w{i}" for i in range(500))
    chunks = chunk_structure([sec("A", text)], max_words=100, overlap=20)
    assert len(chunks) >= 5
    assert all(len(c["text"].split()) <= 100 for c in chunks)
    a, b = chunks[0]["text"].split(), chunks[1]["text"].split()
    assert a[-20:] == b[:20]

def test_chunks_never_cross_section_boundaries():
    chunks = chunk_structure([sec("A", "alpha text"), sec("B", "beta text")])
    assert [c["heading_path"] for c in chunks] == ["A", "B"]

def test_short_paragraphs_are_packed_together():
    chunks = chunk_structure([sec("A", "one para\n\ntwo para")])
    assert len(chunks) == 1

def test_fixed_strategy_loses_headings():
    chunks = chunk_fixed([sec("A", "alpha text"), sec("B", "beta text")])
    assert chunks[0]["heading_path"] == "(fixed)"

def test_chunk_ids_are_deterministic():
    s = [sec("A", "alpha text")]
    assert build_chunks("v1", s)[0]["chunk_id"] == build_chunks("v1", s)[0]["chunk_id"]