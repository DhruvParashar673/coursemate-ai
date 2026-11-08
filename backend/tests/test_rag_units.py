"""Unit tests for the RAG layer. Run from backend/:  python -m tests.test_rag_units

Needs no MongoDB. Uses a REAL ChromaDB (temporary directory) and generated PDFs.
Anything that touches an embedding model uses the MOCK embedder (tests/mock_embedder.py).
"""
import os
import random
import secrets
import subprocess
import sys
import tempfile
import threading
import warnings

warnings.filterwarnings("ignore")
_TMP = tempfile.mkdtemp(prefix="cm_unit_")
os.environ.update(
    MONGODB_URL="mongodb://127.0.0.1:1", DATABASE_NAME="unused", JWT_SECRET_KEY=secrets.token_urlsafe(48),
    CHROMA_PERSIST_DIR=os.path.join(_TMP, "chroma"), UPLOAD_DIR=os.path.join(_TMP, "uploads"),
)
import logging
logging.disable(logging.CRITICAL)
import numpy as np
import pymupdf

from app.rag import chunking, embeddings, ingestion, pdf_extractor, retrieval, text_cleaning, vector_store
from app.rag.errors import (EmbeddingError, IngestionCancelled, PdfCorruptError, PdfEncryptedError,
                            PdfNoTextError, PdfTooManyPagesError, VectorStoreError)
from app.rag.vector_store import ChunkToStore
from tests import mock_embedder

results = []
def check(name, cond, extra=""):
    results.append(bool(cond)); print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if (extra and not cond) else ""))
def raises(exc, fn, *a, **k):
    try: fn(*a, **k)
    except exc: return True
    except Exception: return False
    return False

print("=== text cleaning ===")
c = text_cleaning.clean_page_text
check("ligatures normalised (NFKC)", c("\ufb01nd the \ufb02ow") == "find the flow")
check("line-end hyphenation rejoined", c("an exam-\nple of it") == "an example of it")
check("hyphen before capital NOT joined", c("well-\nKnown") != "wellKnown")
check("wrapped lines joined, paragraph break kept", c("one two\nthree\n\nnext para") == "one two three\n\nnext para")
check("standalone page numbers removed", "12" not in c("Intro text here.\n\n12\n\nMore text here.") and "Page 3 of 10" not in c("Body.\nPage 3 of 10\nMore."))
check("NUL / control / soft-hyphen removed", c("ab\x00c\u00add\x07e") == "abcde")
check("NBSP and runs of whitespace collapsed", c("a\u00a0\u00a0b \t  c") == "a b c")
check("empty and punctuation-only pages -> ''", c("") == "" and c("  \n\n --- \n ") == "" and c("\n42\n") == "")
check("Roman-script Hinglish unchanged", c("Deadlock tab hota hai jab processes wait karte hain.") == "Deadlock tab hota hai jab processes wait karte hain.")
check("Devanagari text preserved", c("नमस्ते दुनिया") == "नमस्ते दुनिया")

print("=== chunking ===")
def covered(chs, n):
    pos = 0
    for ch in chs:
        if ch.start > pos: return False
        pos = max(pos, ch.end)
    return bool(chs) and chs[0].start == 0 and pos == n
sentences = [f"Sentence number {i} explains operating system concept {i} in some detail." for i in range(120)]
long_text = " ".join(sentences)
ch = chunking.chunk_text(long_text, 7, 1000, 150)
check("single short chunk covers whole text", (lambda x: len(x) == 1 and x[0].start == 0 and x[0].end == len("hello world") and x[0].page_number == 3)(chunking.chunk_text("hello world", 3, 1000, 150)))
check("long text: contiguous coverage, nothing lost", covered(ch, len(long_text)), (len(ch), ch[0].start, ch[-1].end, len(long_text)))
check("every chunk <= chunk_size, non-empty, tagged with page", all(0 < len(x.text) <= 1000 and x.page_number == 7 for x in ch))
check("consecutive chunks overlap (~150 chars)", all(0 < (a.end - b.start) <= 150 for a, b in zip(ch, ch[1:])), [(a.end - b.start) for a, b in zip(ch, ch[1:])][:6])
check("chunks end on sentence/whitespace boundaries", all(long_text[x.end - 1] in " ." or x.end == len(long_text) for x in ch))
check("chunks start on word boundaries", all(x.start == 0 or long_text[x.start - 1].isspace() for x in ch))
hing = " ".join(["Deadlock tab hota hai jab do ya zyada processes ek dusre ke resources ka wait karte rehte hain." for _ in range(40)])
hc = chunking.chunk_text(hing, 1, 1000, 150); check("Hinglish text chunks cover everything", covered(hc, len(hing)) and all(len(x.text) <= 1000 for x in hc))
blob = "a" * 3500; bc = chunking.chunk_text(blob, 1, 1000, 150); check("no-whitespace string: hard split, terminates, covers all", covered(bc, 3500) and all(len(x.text) <= 1000 for x in bc), len(bc))
check("invalid overlap rejected", raises(ValueError, chunking.chunk_text, "x" * 50, 1, 1000, 600))
pages = [(1, "First page text. " * 5), (2, ""), (3, "Third page text. " * 5)]
cp = chunking.chunk_pages([(n, t.strip()) for n, t in pages], 1000, 150)
check("chunk_pages keeps page numbers; empty page yields no chunk", [x.page_number for x in cp] == [1, 3])
rnd = random.Random(7); bad = 0
for _ in range(300):
    size = rnd.randint(200, 1200); ov = rnd.randint(0, size // 2); n = rnd.randint(0, 6000)
    words = [rnd.choice(["alpha", "beta.", "gamma", "delta?", "x", "longerword", "z" * rnd.randint(1, 40)]) for _ in range(n // 5 + 1)]
    t = " ".join(words)[:n].strip()
    out = chunking.chunk_text(t, 1, size, ov)
    if t and (not covered(out, len(t)) or any(len(x.text) > size for x in out)): bad += 1
check("randomised 300 cases: full coverage + size bound + termination", bad == 0, bad)

print("=== PDF extraction (PyMuPDF, generated PDFs) ===")
def make_pdf(page_texts):
    d = pymupdf.open()
    for t in page_texts:
        p = d.new_page()
        if t: p.insert_text((72, 72), t)
    return d
def write(doc, name, **kw):
    path = os.path.join(_TMP, name); doc.save(path, **kw); return path
good = write(make_pdf(["Page one: processes and threads.", "", "Page three: deadlock detection."]), "good.pdf")
raw = pdf_extractor.extract_pages(good, 500)
check("page count + original page numbers preserved", raw.page_count == 3 and [p.page_number for p in raw.pages] == [1, 2, 3])
check("text mapped to the right physical page (blank page 2 stays blank)", "processes" in raw.pages[0].text and raw.pages[1].text.strip() == "" and "deadlock" in raw.pages[2].text)
prep = ingestion.prepare_document("a" * 24, raw, 1000, 150)
check("prepared chunks keep page numbers; pages_without_text counted", [c.page_number for c in prep.chunks] == [1, 3] and prep.pages_without_text == 1 and prep.page_count == 3)
check("chunk ids unique + deterministic format", len({c.chunk_id for c in prep.chunks}) == len(prep.chunks) and prep.chunks[0].chunk_id == "a" * 24 + "_00000")
ingestion.ensure_extractable(prep, 0.1); check("PDF with text accepted", True)
pm = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 200, 200), False); pm.set_rect(pm.irect, (255, 255, 255))
sc = pymupdf.open(); sp = sc.new_page(); sp.insert_image(sp.rect, pixmap=pm)
scanned = write(sc, "scanned.pdf"); sprep = ingestion.prepare_document("b" * 24, pdf_extractor.extract_pages(scanned, 500), 1000, 150)
check("scanned/image-only PDF rejected as no-text", raises(PdfNoTextError, ingestion.ensure_extractable, sprep, 0.1))
mostly = write(make_pdf(["Only this page has text."] + [""] * 19), "mostly_scanned.pdf")
mp = ingestion.prepare_document("c" * 24, pdf_extractor.extract_pages(mostly, 500), 1000, 150)
check("1 text page out of 20 (5% < 10%) rejected", raises(PdfNoTextError, ingestion.ensure_extractable, mp, 0.1))
enc = write(make_pdf(["secret"]), "enc.pdf", encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="pw", owner_pw="ow")
check("password-protected PDF rejected", raises(PdfEncryptedError, pdf_extractor.extract_pages, enc, 500))
junk = os.path.join(_TMP, "junk.pdf"); open(junk, "wb").write(b"%PDF-1.7\nthis is not a real pdf at all")
check("corrupt file rejected", raises(PdfCorruptError, pdf_extractor.extract_pages, junk, 500))
many = write(make_pdf([f"page {i}" for i in range(6)]), "many.pdf")
check("page limit enforced", raises(PdfTooManyPagesError, pdf_extractor.extract_pages, many, 5))
errs = []
def worker(): 
    try: pdf_extractor.extract_pages(good, 500)
    except Exception as e: errs.append(e)
ts = [threading.Thread(target=worker) for _ in range(8)]; [t.start() for t in ts]; [t.join() for t in ts]
check("concurrent extraction (global lock) is safe", errs == [])

print("=== embeddings wrapper (MOCK model) ===")
P = embeddings.resolve_prefixes
check("e5 model -> 'query: ' / 'passage: '", P("intfloat/multilingual-e5-small", None, None) == embeddings.Prefixes("query: ", "passage: "))
check("explicit prefix overrides win", P("intfloat/multilingual-e5-small", "q> ", "p> ") == embeddings.Prefixes("q> ", "p> "))
check("unknown model -> no prefixes unless configured", P("some/other-model", None, None) == embeddings.Prefixes("", "") and P("some/other-model", "Q:", None).query == "Q:")
mock = mock_embedder.install(); emb = embeddings.get_embedder()
docs = emb.embed_documents(["alpha beta", "gamma delta"]); q = emb.embed_query("what is alpha")
check("documents get 'passage: ' prefix, query gets 'query: ' prefix (configured default model is e5)", mock.seen_texts == ["passage: alpha beta", "passage: gamma delta", "query: what is alpha"], mock.seen_texts)
check("vectors are 384-d and unit length", len(docs) == 2 and len(docs[0]) == 384 and abs(np.linalg.norm(docs[0]) - 1) < 1e-4 and abs(np.linalg.norm(q) - 1) < 1e-4 and emb.dimension == 384)
check("empty input -> empty output, no model call", (lambda n: (emb.embed_documents([]) == [] and len(mock.seen_texts) == n))(len(mock.seen_texts)))
embeddings._embedder = None; mock_embedder.install(mock_embedder.MockSentenceTransformer(fail=True))
check("model failure surfaces as EmbeddingError (no raw message)", raises(EmbeddingError, embeddings.get_embedder().embed_query, "x"))
def boom(name): raise OSError("/secret/path/model missing")
embeddings._embedder = None; embeddings._load_model = boom
try: embeddings.get_embedder(); msg = ""
except EmbeddingError as e: msg = str(e)
check("model load failure -> EmbeddingError without internal path", msg and "/secret" not in msg, msg)
mock = mock_embedder.install(); embeddings.get_embedder()

print("=== vector store: real ChromaDB, isolation ===")
rng = np.random.default_rng(0)
def vec(seed): v = np.random.default_rng(seed).normal(size=384); return (v / np.linalg.norm(v)).tolist()
def chunks_for(doc, n=3, page0=1): return [ChunkToStore(f"{doc}_{i:05d}", i, page0 + i, f"text {doc} {i}") for i in range(n)]
U1, U2 = "1" * 24, "2" * 24; C1, C2, C3 = "a1" * 12, "b2" * 12, "c3" * 12; D1, D2, D3 = "d1" * 12, "d2" * 12, "d3" * 12
vector_store.add_chunks(U1, C1, D1, chunks_for(D1), [vec(1), vec(2), vec(3)])
vector_store.add_chunks(U1, C2, D2, chunks_for(D2), [vec(1), vec(2), vec(3)])   # same vectors, other course
vector_store.add_chunks(U2, C3, D3, chunks_for(D3), [vec(1), vec(2), vec(3)])   # same vectors, other user
col = vector_store.get_collection()
meta = col.get(ids=[f"{D1}_00001"], include=["metadatas", "documents"])["metadatas"][0]
check("chunk metadata has user_id, course_id, document_id, page_number, chunk_id", {"user_id", "course_id", "document_id", "page_number", "chunk_id"} <= set(meta) and meta["user_id"] == U1 and meta["course_id"] == C1 and meta["page_number"] == 2 and meta["chunk_id"] == f"{D1}_00001", meta)
check("collection uses cosine space and records the embedding model", col.configuration["hnsw"]["space"] == "cosine" and col.metadata["embedding_model"] == "intfloat/multilingual-e5-small")
r = vector_store.query_chunks(U1, C1, vec(1), top_k=10)
check("query scoped to (user, course): only that document, best match first", {x.document_id for x in r} == {D1} and len(r) == 3 and r[0].chunk_id == f"{D1}_00000" and r[0].score > 0.99, [(x.document_id, x.chunk_id) for x in r])
check("same user, other course -> only that course's chunks", {x.document_id for x in vector_store.query_chunks(U1, C2, vec(1), 10)} == {D2})
check("other user cannot see course C1 (even with the right course id)", vector_store.query_chunks(U2, C1, vec(1), 10) == [])
check("user's own course id used with the wrong user -> nothing", vector_store.query_chunks(U2, C2, vec(1), 10) == [])
check("document filter narrows within the scope", vector_store.query_chunks(U1, C1, vec(1), 10, document_id=D2) == [])
check("empty/None ids rejected (no unscoped access possible)", raises(ValueError, vector_store.query_chunks, "", C1, vec(1)) and raises(ValueError, vector_store.query_chunks, U1, None, vec(1)) and raises(ValueError, vector_store.delete_course_chunks, "", ""))
vector_store.delete_document_chunks(U2, C1, D1)
check("delete with wrong owner removes nothing", vector_store.count_document_chunks(U1, C1, D1) == 3)
vector_store.add_chunks(U1, C1, D1, chunks_for(D1), [vec(1), vec(2), vec(3)])
check("re-adding the same chunk ids is idempotent (upsert)", vector_store.count_document_chunks(U1, C1, D1) == 3 and col.count() == 9)
vector_store.delete_document_chunks(U1, C1, D1)
check("delete removes only that document's chunks", vector_store.count_document_chunks(U1, C1, D1) == 0 and vector_store.count_document_chunks(U1, C2, D2) == 3 and vector_store.count_document_chunks(U2, C3, D3) == 3)
vector_store.delete_course_chunks(U1, C2)
check("course delete is scoped to that user+course", vector_store.count_document_chunks(U1, C2, D2) == 0 and vector_store.count_document_chunks(U2, C3, D3) == 3)
ev = threading.Event(); ev.set()
check("cancel flag aborts a write before anything is stored", raises(IngestionCancelled, vector_store.add_chunks, U1, C1, D1, chunks_for(D1), [vec(1), vec(2), vec(3)], ev) and vector_store.count_document_chunks(U1, C1, D1) == 0)
check("length mismatch rejected", raises(ValueError, vector_store.add_chunks, U1, C1, D1, chunks_for(D1), [vec(1)]))
check("wrong embedding dimension -> VectorStoreError", raises(VectorStoreError, vector_store.add_chunks, U1, C1, D1, chunks_for(D1, 1), [[0.1, 0.2]]))
vector_store.add_chunks(U1, C1, D1, chunks_for(D1), [vec(1), vec(2), vec(3)])
col.modify(metadata={"embedding_model": "some/other-model"}); vector_store._collection = None
check("embedding-model mismatch refused (no silent mixing of vector spaces)", raises(VectorStoreError, vector_store.get_collection))
col.modify(metadata={"embedding_model": "intfloat/multilingual-e5-small"}); vector_store._collection = None
check("restored metadata -> opens again", vector_store.get_collection() is not None)
probe = subprocess.run([sys.executable, "-c", f"""
import os, warnings, logging; warnings.filterwarnings('ignore'); logging.disable(logging.CRITICAL)
from app.rag import vector_store
print(vector_store.count_document_chunks('{U1}', '{C1}', '{D1}'), len(vector_store.query_chunks('{U1}', '{C1}', {vec(1)}, 5)))
"""], capture_output=True, text=True, env=dict(os.environ), cwd=os.getcwd())
check("data persists across a process restart (fresh interpreter)", probe.stdout.strip() == "3 3", (probe.stdout, probe.stderr[-200:]))

print("=== embed_and_store + retrieval plumbing (MOCK embedder: lexical, says nothing about real quality) ===")
mock = mock_embedder.install(); vector_store.delete_course_chunks(U1, C1)
texts = ["deadlock needs four conditions mutual exclusion hold and wait", "binary search halves a sorted array each step", "deadlock needs four conditions mutual exclusion hold and wait"]
ch2 = [ChunkToStore(f"{D1}_{i:05d}", i, i + 1, t) for i, t in enumerate(texts)]
n = ingestion.embed_and_store(U1, C1, D1, ch2)
check("embed_and_store returns the stored count", n == 3 and vector_store.count_document_chunks(U1, C1, D1) == 3)
check("duplicate chunk texts embedded only once", sum(1 for t in mock.seen_texts if "deadlock" in t) == 1 and len(mock.seen_texts) == 2, mock.seen_texts)
check("indexing used the 'passage: ' prefix", all(t.startswith("passage: ") for t in mock.seen_texts))
hits = retrieval.search_chunks(U1, C1, "four conditions for deadlock", top_k=2)
check("search_chunks: query prefix applied + scoped result", mock.seen_texts[-1] == "query: four conditions for deadlock" and hits[0].page_number in (1, 3) and {h.document_id for h in hits} == {D1})
check("search_chunks for another user/course returns nothing", retrieval.search_chunks(U2, C1, "deadlock") == [] and retrieval.search_chunks(U1, C2, "deadlock") == [])
check("blank query rejected", raises(ValueError, retrieval.search_chunks, U1, C1, "   "))

print(f"\n{sum(results)}/{len(results)} passed"); sys.exit(0 if all(results) else 1)
