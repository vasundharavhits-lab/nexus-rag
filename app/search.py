# app/search.py
import math, re
from app import vectorstore
from app.embeddings import embed_query
import app.embeddings as _emb

BASE = ("FROM chunks c "
        "JOIN document_versions v ON v.version_id = c.version_id "
        "JOIN documents d ON d.document_id = v.document_id ")
COLS = ("c.chunk_id, c.version_id, c.idx, c.strategy, d.logical_name, v.label, v.filename, "
        "c.heading_path, c.page, c.text, v.doc_status, v.effective_at")

# "practice query set 15", "section 3", "step 7": a few words followed by a standalone number.
_NUM_REF = re.compile(r"((?:[A-Za-z]+\s+){1,3})(\d+)(?![\w.-])")

# Words that carry no topic in the most common languages of this app. This is only a first filter: words
# that occur in a large share of the passages are also dropped automatically (see _term_weights), so the
# search works for any language without a word list.
_STOP = frozenset("""a an the is are was were be been do does did can could would will shall should may might
why what who whom how when where which that this these those it its they them their he she his her we you your
i me my to of in on at by for from with as and or not no nor so than then there here into out up about over
under again once only own same too very s t just don now also any each other some such if but because""".split())

_SEP = re.compile(r"[\s\-\u2013\u2014,;:!?()\[\]{}\"'\u201c\u201d\u2018\u2019|\u0964\u0965./\\<>=+*#@~_`]+")


def numbered_phrase(query):
    """Return the exact phrase to look for when the question names a numbered item, else None."""
    m = _NUM_REF.search(query)
    return (m.group(1) + m.group(2)).strip() if m else None


def query_terms(query, limit=24):
    """Search words of a question in any script: split on spaces/punctuation (letters, combining marks and
    digits stay together), lower-cased, without very common English words."""
    seen, out = set(), []
    for t in _SEP.split(query or ""):
        t = t.lower().strip()
        if len(t) < 2 and not t.isdigit():
            continue
        if t in _STOP or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out[:limit]


def phrase_search(con, workspace_id, phrase, k=5, strategy="structure"):
    """Adjacent-words match (so 'set 15' cannot be satisfied by 'set 30'), ranked by cover density."""
    return con.execute(
        "WITH q AS (SELECT phraseto_tsquery('simple', %s) AS query) "
        f"SELECT {COLS}, ts_rank_cd(c.tsv, q.query) AS score {BASE}, q "
        "WHERE d.workspace_id=%s AND c.strategy=%s AND c.tsv @@ q.query "
        "ORDER BY score DESC LIMIT %s",
        (phrase, workspace_id, strategy, k)).fetchall()


def _term_weights(con, workspace_id, terms, strategy):
    """{term: weight}: rare words weigh more, words in most passages are dropped (they are stop words in
    whatever language the documents use). Computed from the workspace itself, so no language lists."""
    if not terms:
        return {}
    n = con.execute("SELECT count(*) AS n " + BASE + "WHERE d.workspace_id=%s AND c.strategy=%s",
                    (workspace_id, strategy)).fetchone()["n"]
    if not n:
        return {}
    rows = con.execute(
        "SELECT u.term, (SELECT count(*) " + BASE +
        "WHERE d.workspace_id=%s AND c.strategy=%s AND c.tsv @@ plainto_tsquery('simple', u.term)) AS df "
        "FROM unnest(%s::text[]) AS u(term)", (workspace_id, strategy, terms)).fetchall()
    out = {}
    for r in rows:
        df = r["df"]
        if df <= 0:
            continue
        if n >= 20 and df / n > 0.35:
            continue                                   # in a third of all passages: says nothing
        out[r["term"]] = math.log(1 + n / df)
    # keep the most informative words
    best = sorted(out.items(), key=lambda kv: -kv[1])[:14]
    return dict(best)


def keyword_search(con, workspace_id, query, k=5, strategy="structure"):
    phrase = numbered_phrase(query)
    if phrase:                                   # numbered reference: exact phrase first
        rows = phrase_search(con, workspace_id, phrase, k, strategy)
        if rows:                                 # nothing matched -> fall back to word matching
            return rows
    terms = query_terms(query)
    weights = _term_weights(con, workspace_id, terms, strategy)
    if not weights:
        return []
    names, ws = list(weights), list(weights.values())
    return con.execute(
        "WITH t AS (SELECT term, w FROM unnest(%s::text[], %s::float8[]) AS u(term, w)), "
        "q AS (SELECT string_agg('(' || plainto_tsquery('simple', term)::text || ')', ' | ')::tsquery AS query FROM t) "
        f"SELECT {COLS}, "
        "(SELECT coalesce(sum(t.w), 0) FROM t WHERE c.tsv @@ plainto_tsquery('simple', t.term)) AS score "
        f"{BASE}, q "
        "WHERE d.workspace_id=%s AND c.strategy=%s AND c.tsv @@ q.query "
        "ORDER BY score DESC, c.idx LIMIT %s",
        (names, ws, workspace_id, strategy, k)).fetchall()


def rows_by_ids(con, chunk_ids):
    if not chunk_ids:
        return {}
    rows = con.execute(f"SELECT {COLS} {BASE} WHERE c.chunk_id = ANY(%s)", (list(chunk_ids),)).fetchall()
    return {r["chunk_id"]: r for r in rows}


def vector_search(con, workspace_id, query, k=5, strategy="structure"):
    if not vectorstore.has_vectors(con, workspace_id, strategy):
        return []                              # nothing embedded yet: keyword search still works
    qv = embed_query(query)
    hits = vectorstore.top_k(con, workspace_id, qv, k, strategy, model=_emb.EMBED_MODEL)
    if not hits:
        return []
    found = rows_by_ids(con, [cid for cid, _ in hits])
    results = []
    for cid, score in hits:
        r = found.get(cid)
        if r:
            r = dict(r)
            r["score"] = float(score)
            results.append(r)
    return results
