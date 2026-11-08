"""REAL-MODEL verification. Run locally from backend/ (needs internet the first time to download the model):

    python scripts/verify_real_embeddings.py                  # uses EMBEDDING_MODEL_NAME (default: intfloat/multilingual-e5-small)
    python scripts/verify_real_embeddings.py --model <name-or-local-path> --top-k 3

What it does (no MongoDB, no network calls other than the model download, nothing in your real chroma_db):
  1. loads the real model through app/rag/embeddings.py and checks dimension, normalisation and the
     "passage: " / "query: " prefixes actually reaching the model;
  2. indexes English and Roman-script Hinglish passages through the real chunk -> embed -> Chroma pipeline;
  3. runs English and Hinglish queries and reports hit@1 / hit@3 / MRR per query language;
  4. checks that another user's identical chunks are never returned (isolation) and that deletion works.

Exit code: non-zero only for STRUCTURAL failures (prefixes, dimension, isolation, deletion).
Retrieval quality is REPORTED, not asserted - you judge it. Do not treat it as verified until you have read it.
"""
import argparse, os, sys, tempfile, time, warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

parser = argparse.ArgumentParser()
parser.add_argument("--model", default=None, help="HF model id or local path (default: EMBEDDING_MODEL_NAME / app default)")
parser.add_argument("--top-k", type=int, default=3)
args = parser.parse_args()

# Harmless placeholders so app settings load even without a .env; MongoDB is never contacted.
os.environ.setdefault("MONGODB_URL", "mongodb://unused.invalid")
os.environ.setdefault("DATABASE_NAME", "unused")
os.environ.setdefault("JWT_SECRET_KEY", "verify-script-placeholder-not-a-real-secret-0123456789")
_tmp = tempfile.mkdtemp(prefix="cm_verify_")
os.environ["CHROMA_PERSIST_DIR"] = os.path.join(_tmp, "chroma")  # never touch the real chroma_db
os.environ["CHROMA_COLLECTION_NAME"] = "verify_chunks"
if args.model:
    os.environ["EMBEDDING_MODEL_NAME"] = args.model

import logging
logging.getLogger().setLevel(logging.ERROR)
import numpy as np

from app.core.config import get_settings
from app.rag import chunking, ingestion, retrieval, text_cleaning, vector_store
from app.rag.embeddings import get_embedder
from app.rag.vector_store import ChunkToStore

structural = []
def check(name, ok, detail=""):
    structural.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (f"   [{detail}]" if (detail and not ok) else ""))

# (topic, language, passage)
CORPUS = [
 ("deadlock", "EN", "A deadlock occurs when two or more processes wait forever for resources held by each other. Four conditions must hold at the same time: mutual exclusion, hold and wait, no preemption and circular wait. Breaking any one of them prevents deadlock."),
 ("deadlock", "HI", "Deadlock tab hota hai jab do ya zyada processes ek dusre ke resources ka wait karte rehte hain aur koi bhi aage nahi badh pata. Deadlock ke liye four conditions chahiye: mutual exclusion, hold and wait, no preemption aur circular wait. In mein se ek bhi condition tod do to deadlock avoid ho sakta hai."),
 ("binary_search", "EN", "Binary search works only on a sorted array. It compares the key with the middle element and discards half of the array at every step, so the time complexity is O(log n), much faster than linear search."),
 ("binary_search", "HI", "Binary search sirf sorted array par kaam karta hai. Isme hum beech wale element se key ko compare karte hain, agar key chhoti hai to left half mein dhundhte hain warna right half mein. Isliye time complexity O(log n) hoti hai, linear search se bahut tez."),
 ("normalization", "EN", "Database normalization reduces redundancy and avoids update anomalies. First normal form requires atomic column values, second normal form removes partial dependencies and third normal form removes transitive dependencies."),
 ("normalization", "HI", "Database normalization ka matlab hai data ki redundancy kam karna aur anomalies se bachna. First normal form mein har column ki value atomic honi chahiye. Second normal form mein partial dependency hatate hain aur third normal form mein transitive dependency."),
 ("gradient_descent", "EN", "Gradient descent is an optimization algorithm that updates the parameters in the direction opposite to the gradient of the loss function. A learning rate that is too large can make training diverge, while one that is too small makes it very slow."),
 ("gradient_descent", "HI", "Gradient descent ek optimization algorithm hai jisme hum loss function ko kam karne ke liye parameters ko gradient ki ulti direction mein update karte hain. Learning rate bahut bada ho to model diverge kar sakta hai aur bahut chhota ho to training slow ho jaati hai."),
 ("tcp_udp", "EN", "TCP is a reliable, connection-oriented protocol that keeps packets in order and retransmits lost ones. UDP is connectionless and gives no guarantees, but it is fast, which is why it is used for video streaming and online games."),
 ("tcp_udp", "HI", "TCP ek reliable protocol hai jo connection banata hai, packets ka order maintain karta hai aur lost packets dobara bhejta hai. UDP connectionless hai, isme guarantee nahi hoti lekin yeh fast hai, isliye video streaming aur gaming mein use hota hai."),
 ("recursion", "EN", "In recursion a function calls itself on a smaller version of the problem. Every recursive function needs a base case, otherwise infinite recursion ends in a stack overflow. Factorial and Fibonacci are classic examples."),
 ("recursion", "HI", "Recursion mein ek function apne aap ko call karta hai chhote problem ke saath. Har recursive function mein base case zaroori hota hai, warna infinite recursion se stack overflow ho jata hai. Factorial aur Fibonacci iske classic examples hain."),
]
QUERIES = [
 ("EN", "What are the four conditions required for a deadlock?", "deadlock"),
 ("EN", "How does binary search achieve logarithmic time?", "binary_search"),
 ("EN", "What is the difference between 1NF, 2NF and 3NF?", "normalization"),
 ("EN", "Why can a large learning rate make gradient descent diverge?", "gradient_descent"),
 ("EN", "Why is UDP preferred for video streaming?", "tcp_udp"),
 ("EN", "What happens if a recursive function has no base case?", "recursion"),
 ("HI", "deadlock hone ke liye kaun si chaar conditions chahiye?", "deadlock"),
 ("HI", "binary search mein time complexity log n kyun hoti hai?", "binary_search"),
 ("HI", "normalization mein 1NF 2NF aur 3NF ka matlab kya hai?", "normalization"),
 ("HI", "learning rate bahut bada ho to gradient descent mein kya hota hai?", "gradient_descent"),
 ("HI", "video streaming ke liye UDP kyun use karte hain?", "tcp_udp"),
 ("HI", "recursion mein base case na ho to kya hoga?", "recursion"),
 ("HI", "mujhe sorted array mein element dhundhne ka tez tarika batao", "binary_search"),
 ("HI", "do processes ek dusre ka wait karte rahe to kya problem hoti hai?", "deadlock"),
]
U1, U2 = "1" * 24, "2" * 24
C1, C2 = "a1" * 12, "b2" * 12
D1, D2 = "d1" * 12, "d2" * 12

settings = get_settings()
print(f"Model: {settings.EMBEDDING_MODEL_NAME}\nLoading (first run downloads it) ...")
t0 = time.time(); emb = get_embedder(); print(f"Loaded in {time.time() - t0:.1f}s | dimension {emb.dimension} | prefixes query={emb.prefixes.query!r} passage={emb.prefixes.passage!r}")

seen = []
_orig = emb._model.encode
def spy(texts, *a, **k):
    seen.extend(texts if not isinstance(texts, str) else [texts]); return _orig(texts, *a, **k)
emb._model.encode = spy

print("\n--- structure ---")
if "e5" in settings.EMBEDDING_MODEL_NAME.lower():
    check("E5 prefixes are 'query: ' and 'passage: '", emb.prefixes.query == "query: " and emb.prefixes.passage == "passage: ")
if settings.EMBEDDING_MODEL_NAME == "intfloat/multilingual-e5-small":
    check("dimension is 384 (multilingual-e5-small)", emb.dimension == 384, emb.dimension)
vecs = emb.embed_documents(["hello world", "namaste duniya"])
check("embeddings are unit length (normalised)", all(abs(np.linalg.norm(v) - 1) < 1e-3 for v in vecs))
tok = getattr(emb._model, "tokenizer", None); max_len = getattr(emb._model, "max_seq_length", None)
if tok is not None and max_len:
    longest = max(CORPUS, key=lambda c: len(c[2]))[2] * 2  # ~1000+ chars of the longest passage text
    n_tok = len(tok(longest[:1000])["input_ids"])
    print(f"info: a 1000-character Hinglish/English chunk is ~{n_tok} tokens (model max_seq_length = {max_len})")
    check("1000-character chunks fit the model's token limit (no silent truncation)", n_tok <= max_len, f"{n_tok} > {max_len}")

print("\n--- indexing through the real pipeline ---")
cleaned = [(i + 1, text_cleaning.clean_page_text(c[2])) for i, c in enumerate(CORPUS)]
page_meta = {i + 1: (c[0], c[1]) for i, c in enumerate(CORPUS)}
chunks = [ChunkToStore(f"{D1}_{i:05d}", i, ch.page_number, ch.text) for i, ch in enumerate(chunking.chunk_pages(cleaned, settings.CHUNK_SIZE_CHARS, settings.CHUNK_OVERLAP_CHARS))]
n = ingestion.embed_and_store(U1, C1, D1, chunks)
n2 = ingestion.embed_and_store(U2, C2, D2, [ChunkToStore(f"{D2}_{c.chunk_index:05d}", c.chunk_index, c.page_number, c.text) for c in chunks])  # same text, another user
check("chunks stored for both users", n == n2 == len(chunks) == len(CORPUS), (n, n2, len(chunks)))
check("every indexed text carried the passage prefix when it reached the model", all(t.startswith(emb.prefixes.passage) for t in seen if t not in ("hello world", "namaste duniya") and not t.startswith(emb.prefixes.query)))

print(f"\n--- retrieval (top-{args.top_k}); topic match counts as a hit, either language ---")
stats = {"EN": [], "HI": []}; same_lang = {"EN": [], "HI": []}
seen.clear()
for lang, query, topic in QUERIES:
    hits = retrieval.search_chunks(U1, C1, query, top_k=args.top_k)
    topics = [page_meta[h.page_number][0] for h in hits]
    rank = topics.index(topic) + 1 if topic in topics else None
    stats[lang].append(rank); top_lang = page_meta[hits[0].page_number][1]; same_lang[lang].append(top_lang == lang)
    print(f"[{lang}] rank={rank if rank else '>' + str(args.top_k)}  top1={page_meta[hits[0].page_number][0]}/{top_lang} ({hits[0].score:.3f})  | {query}")
check("every query reached the model with the 'query: ' prefix", all(t.startswith(emb.prefixes.query) for t in seen) and len(seen) == len(QUERIES))
print("\nSummary (informative only - NOT asserted):")
for lang, name in (("EN", "English queries "), ("HI", "Hinglish queries")):
    r = stats[lang]; h1 = sum(1 for x in r if x == 1) / len(r); h3 = sum(1 for x in r if x) / len(r); mrr = sum(1 / x for x in r if x) / len(r)
    print(f"  {name}: hit@1 {h1:.0%} | hit@{args.top_k} {h3:.0%} | MRR {mrr:.2f} | top-1 in the query's own language {sum(same_lang[lang]) / len(r):.0%}")

print("\n--- isolation and deletion ---")
all_ids = set()
for _, query, _ in QUERIES:
    all_ids |= {h.document_id for h in retrieval.search_chunks(U1, C1, query, top_k=50)}
check("user 1 / course 1 never receives user 2's identical chunks", all_ids == {D1}, all_ids)
check("user 2 cannot read course 1; user 1 cannot read course 2", retrieval.search_chunks(U2, C1, "deadlock") == [] and retrieval.search_chunks(U1, C2, "deadlock") == [])
vector_store.delete_document_chunks(U1, C1, D1)
check("deleting user 1's document removes only its chunks", vector_store.count_document_chunks(U1, C1, D1) == 0 and vector_store.count_document_chunks(U2, C2, D2) == len(chunks))
import shutil; shutil.rmtree(_tmp, ignore_errors=True)
print(f"\nStructural checks: {sum(structural)}/{len(structural)} passed.")
print("Quality: read the table above. This script cannot tell you whether the numbers are good enough for your use.")
sys.exit(0 if all(structural) else 1)
