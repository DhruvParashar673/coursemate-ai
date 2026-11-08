"""End-to-end API tests for Module 4. Run from backend/ with a THROWAWAY MongoDB:

    TEST_MONGODB_URL=mongodb://127.0.0.1:27017 python -m tests.test_documents_api_mock_embedder

Uses a random database name (dropped at the end), temporary upload/Chroma directories, a real
ChromaDB and generated PDFs. EVERY embedding in this file comes from the MOCK embedder
(tests/mock_embedder.py): it verifies plumbing, ownership, deletion and failure handling,
NOT retrieval quality and NOT the real e5 model. Never point TEST_MONGODB_URL at data you care about.
"""
import asyncio, os, secrets, sys, tempfile, threading, uuid, warnings
warnings.filterwarnings("ignore")

TEST_MONGO = os.environ.get("TEST_MONGODB_URL")
if not TEST_MONGO:
    sys.exit("Set TEST_MONGODB_URL to a throwaway MongoDB (a random database inside it is created and dropped).")
_TMP = tempfile.mkdtemp(prefix="cm_api_")
DB = "cm_doc_test_" + secrets.token_hex(4)
os.environ.update(MONGODB_URL=TEST_MONGO, DATABASE_NAME=DB, JWT_SECRET_KEY=secrets.token_urlsafe(48),
                  UPLOAD_DIR=os.path.join(_TMP, "uploads"), CHROMA_PERSIST_DIR=os.path.join(_TMP, "chroma"),
                  MAX_UPLOAD_SIZE_MB="1", MAX_PDF_PAGES="5")
import logging; logging.disable(logging.CRITICAL)
import httpx, jwt, pymupdf
from datetime import datetime, timedelta, timezone
from bson import ObjectId
from app.main import app
from app.core.config import get_settings
from app.core.database import get_database
from app.rag import vector_store, retrieval, embeddings
from app.rag.errors import VectorStoreError
from app.services import document as docsvc
from tests import mock_embedder
from tests.mock_embedder import MockSentenceTransformer

SETTINGS = get_settings(); UPLOADS = SETTINGS.UPLOAD_DIR
results = []; error_bodies = []
def check(name, cond, extra=""):
    results.append(bool(cond)); print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if (extra and not cond) else ""))

def pdf(pages):
    d = pymupdf.open()
    for t in pages:
        p = d.new_page()
        if t: p.insert_text((72, 72), t)
    return d.tobytes()
def uniq(): return uuid.uuid4().hex[:10]
def doc_pdf(tag=None): 
    tag = tag or uniq()
    return pdf([f"{tag} Deadlock requires four conditions: mutual exclusion, hold and wait, no preemption, circular wait.", "", f"{tag} Binary search halves a sorted array at every step giving logarithmic time."])
FORBIDDEN_KEYS = {"user_id", "filename", "file_sha256", "embedding_model", "error_code", "_id"}
LEAK = ["/tmp", "/uploads", "uploads/", "traceback", "pymupdf", "chroma", "mongo", "sha256", ".part", DB.lower()]
def scan(resp):
    body = resp.text.lower(); error_bodies.append((resp.status_code, resp.text))
    return not any(t in body for t in LEAK)

async def main():
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t", timeout=60) as c:
            db = get_database(); mock = mock_embedder.install()
            async def mkuser(tag):
                e = f"{tag}@example.com"
                await c.post("/auth/signup", json={"name": tag, "email": e, "password": "password123"})
                lg = (await c.post("/auth/login", json={"email": e, "password": "password123"})).json()
                return lg["user"]["id"], {"Authorization": f"Bearer {lg['access_token']}"}
            async def mkcourse(h, title="Course"): return (await c.post("/courses", json={"title": title}, headers=h)).json()["id"]
            A, hA = await mkuser("alice"); B, hB = await mkuser("bob")
            A1, A2 = await mkcourse(hA, "A1"), await mkcourse(hA, "A2"); B1 = await mkcourse(hB, "B1")
            def up(h, cid, data, name="notes.pdf", ctype="application/pdf", **kw):
                return c.post(f"/courses/{cid}/documents", files={"file": (name, data, ctype)}, headers=h, **kw)
            async def poll(h, cid, did, want, tries=200):
                for _ in range(tries):
                    r = await c.get(f"/courses/{cid}/documents/{did}", headers=h)
                    if r.status_code == 200 and r.json()["status"] in (want if isinstance(want, tuple) else (want,)): return r.json()
                    await asyncio.sleep(0.05)
                return r.json()
            def chunk_count(u, cid, did): return vector_store.count_document_chunks(u, cid, did)
            def pdf_file(u, cid, did): return UPLOADS / u / cid / f"{did}.pdf"
            async def consistency(label):
                col = vector_store.get_collection(); got = col.get(include=["metadatas"])
                docs = {str(d["_id"]): d async for d in db["documents"].find({})}
                bad_chunks = [m["document_id"] for m in got["metadatas"] if m["document_id"] not in docs or docs[m["document_id"]]["user_id"] != m["user_id"] or docs[m["document_id"]]["course_id"] != m["course_id"]]
                files = [p for p in UPLOADS.rglob("*.pdf") if ".tmp" not in p.parts]
                bad_files = [p.name for p in files if p.stem not in docs]
                tmp_left = os.listdir(UPLOADS / ".tmp") if (UPLOADS / ".tmp").exists() else []
                check(f"invariant [{label}]: no orphan chunks, no orphan PDFs, no temp leftovers", not bad_chunks and not bad_files and not tmp_left, (bad_chunks[:2], bad_files[:2], tmp_left[:2]))

            # ---------- 1. unauthenticated ----------
            print("=== 1. unauthenticated / token handling ===")
            some = str(ObjectId()); data = doc_pdf()
            now = datetime.now(timezone.utc); key = os.environ["JWT_SECRET_KEY"]
            tokens = {"no token": {}, "garbage": {"Authorization": "Bearer abc.def.ghi"},
                      "expired": {"Authorization": "Bearer " + jwt.encode({"sub": A, "iat": now - timedelta(hours=2), "exp": now - timedelta(hours=1)}, key, algorithm="HS256")},
                      "unknown user": {"Authorization": "Bearer " + jwt.encode({"sub": str(ObjectId()), "iat": now, "exp": now + timedelta(hours=1)}, key, algorithm="HS256")}}
            for label, h in tokens.items():
                rs = [await up(h, A1, data), await c.get(f"/courses/{A1}/documents", headers=h), await c.get(f"/courses/{A1}/documents/{some}", headers=h), await c.delete(f"/courses/{A1}/documents/{some}", headers=h)]
                check(f"all 4 document endpoints -> 401 ({label})", all(r.status_code == 401 and r.headers.get("www-authenticate") == "Bearer" for r in rs), [r.status_code for r in rs])
            r = await up({}, "not-an-id", data); check("unauthenticated upload to malformed course id -> 401 (auth first)", r.status_code == 401)
            big_ct = await c.post(f"/courses/{A1}/documents", content=b"x" * 10, headers={"Content-Length": str(50 * 1024 * 1024), "Content-Type": "multipart/form-data; boundary=zz"})
            check("unauthenticated + huge Content-Length -> 401, body never read", big_ct.status_code == 401, big_ct.status_code)
            check("nothing was written by unauthenticated attempts", await db["documents"].count_documents({}) == 0)

            # ---------- 2. happy path ----------
            print("=== 2. upload happy path ===")
            data1 = pdf(["Deadlock requires four conditions: mutual exclusion, hold and wait, no preemption, circular wait.", "", "Binary search halves a sorted array at every step giving logarithmic time."])
            r = await up(hA, A1, data1, name="OS Notes.pdf"); body = r.json(); did1 = body.get("document_id")
            check("upload -> 202 Accepted with status 'processing' in the response", r.status_code == 202 and body["status"] == "processing" and body["chunk_count"] == 0, r.text)
            check("Location header points at the new document", r.headers.get("location") == f"/courses/{A1}/documents/{did1}")
            check("response exposes only public fields (no user_id / stored filename / hash / paths)", not (FORBIDDEN_KEYS & set(body)) and body["original_filename"] == "OS Notes.pdf" and body["page_count"] == 3 and body["pages_without_text"] == 1 and body["course_id"] == A1 and body["file_size"] == len(data1), body)
            ready = await poll(hA, A1, did1, "ready")
            check("polling reaches 'ready' with chunk_count > 0", ready["status"] == "ready" and ready["chunk_count"] > 0 and ready["error"] is None, ready)
            check("Chroma holds exactly chunk_count chunks for the document", chunk_count(A, A1, did1) == ready["chunk_count"])
            col = vector_store.get_collection(); meta = col.get(where={"document_id": did1}, include=["metadatas"])["metadatas"]
            check("every chunk: user_id, course_id, document_id, page_number, chunk_id (unique)", all({"user_id", "course_id", "document_id", "page_number", "chunk_id"} <= set(m) and m["user_id"] == A and m["course_id"] == A1 for m in meta) and len({m["chunk_id"] for m in meta}) == len(meta) and sorted({m["page_number"] for m in meta}) == [1, 3], sorted({m["page_number"] for m in meta}))
            m = await db["documents"].find_one({"_id": ObjectId(did1)})
            check("Mongo record: all required fields, server-generated stored filename", m["filename"] == f"{did1}.pdf" and m["original_filename"] == "OS Notes.pdf" and m["user_id"] == A and m["course_id"] == A1 and m["file_size"] == len(data1) and m["page_count"] == 3 and m["chunk_count"] == ready["chunk_count"] and m["status"] == "ready" and m["created_at"] and len(m["file_sha256"]) == 64, {k: m[k] for k in ("filename", "status")})
            check("PDF stored at uploads/<user>/<course>/<document_id>.pdf with 0600 permissions", pdf_file(A, A1, did1).read_bytes() == data1 and oct(pdf_file(A, A1, did1).stat().st_mode & 0o777) == "0o600")
            check("passages were embedded with the 'passage: ' prefix (mock saw only prefixed texts)", mock.seen_texts and all(t.startswith("passage: ") for t in mock.seen_texts))
            r = await c.get(f"/courses/{A1}/documents/{did1}", headers=hA); check("GET one document", r.status_code == 200 and r.json()["document_id"] == did1)
            r = await c.get(f"/courses/{A1}/documents", headers=hA); check("GET list includes it", [d["document_id"] for d in r.json()] == [did1])
            await consistency("after first upload")

            # ---------- 3. retrieval plumbing (MOCK) ----------
            print("=== 3. retrieval plumbing (MOCK embedder: lexical overlap only; NOT a quality test) ===")
            hits = await asyncio.to_thread(retrieval.search_chunks, A, A1, "binary search sorted array logarithmic", 3)
            check("[mock] query returns the page-3 chunk first, scoped to the right document", hits and hits[0].page_number == 3 and {h.document_id for h in hits} == {did1}, [(h.page_number, round(h.score, 2)) for h in hits])
            check("[mock] query used the 'query: ' prefix", mock.seen_texts[-1].startswith("query: "))
            hing = pdf(["Deadlock tab hota hai jab do ya zyada processes ek dusre ke resources ka wait karte rehte hain. Recursion mein base case zaroori hota hai."])
            r = await up(hA, A2, hing, name="hinglish.pdf"); hdid = r.json()["document_id"]; await poll(hA, A2, hdid, "ready")
            hh = await asyncio.to_thread(retrieval.search_chunks, A, A2, "deadlock kab hota hai", 2)
            check("[mock] Roman-script Hinglish PDF: extracted, chunked, stored and retrievable end to end (plumbing only)", hh and "Deadlock tab hota hai" in hh[0].text and hh[0].page_number == 1, hh[:1])

            # ---------- 4. duplicates & concurrency ----------
            print("=== 4. duplicates and concurrent uploads ===")
            r = await up(hA, A1, data1, name="same-bytes-new-name.pdf"); check("same PDF again in the same course -> 409", r.status_code == 409 and scan(r) and r.json() == {"detail": "This PDF has already been uploaded to this course"}, r.text)
            dup = doc_pdf(); rs = await asyncio.gather(up(hA, A1, dup), up(hA, A1, dup))
            codes = sorted(x.status_code for x in rs)
            check("two simultaneous identical uploads -> exactly one 202 and one 409", codes == [202, 409], codes)
            win = [x.json()["document_id"] for x in rs if x.status_code == 202][0]; await poll(hA, A1, win, "ready")
            check("race left exactly one record, one PDF and one set of chunks", await db["documents"].count_documents({"course_id": A1, "file_sha256": (await db["documents"].find_one({"_id": ObjectId(win)}))["file_sha256"]}) == 1 and len(list((UPLOADS / A / A1).glob("*.pdf"))) == 2 and chunk_count(A, A1, win) > 0)
            r = await up(hA, A2, data1); check("same PDF in a different course of the same user -> accepted", r.status_code == 202); await poll(hA, A2, r.json()["document_id"], "ready")
            rs = await asyncio.gather(*[up(hA, A1, doc_pdf()) for _ in range(3)]); ids = [x.json()["document_id"] for x in rs]
            check("3 different PDFs uploaded concurrently -> all 202", all(x.status_code == 202 for x in rs))
            fin = [await poll(hA, A1, i, "ready") for i in ids]
            check("all three become ready (jobs run one at a time) with matching chunk counts", all(f["status"] == "ready" and chunk_count(A, A1, f["document_id"]) == f["chunk_count"] > 0 for f in fin))
            await consistency("after concurrency")

            # ---------- 5. validation ----------
            print("=== 5. upload validation ===")
            n_docs = await db["documents"].count_documents({})
            def rej(label, r, code, needle=None):
                ok = r.status_code == code and scan(r) and (needle is None or needle.lower() in r.text.lower())
                check(f"{label} -> {code}", ok, (r.status_code, r.text[:150]))
            rej("wrong extension (.txt)", await up(hA, A1, doc_pdf(), name="notes.txt"), 415)
            rej("wrong MIME (text/plain)", await up(hA, A1, doc_pdf(), ctype="text/plain"), 415)
            rej("wrong MIME (octet-stream)", await up(hA, A1, doc_pdf(), ctype="application/octet-stream"), 415)
            rej("fake PDF (.pdf + application/pdf but wrong signature)", await up(hA, A1, b"hello, I am not a pdf"), 415, "not a PDF")
            rej("empty file", await up(hA, A1, b""), 422, "empty")
            rej("'%PDF-' header followed by garbage", await up(hA, A1, b"%PDF-1.7\nthis is not really a pdf"), 422)
            d = pymupdf.open(); d.new_page().insert_text((72, 72), "secret text"); encb = d.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="pw", owner_pw="ow")
            rej("password-protected PDF", await up(hA, A1, encb), 422, "password")
            pm = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 200, 200), False); pm.set_rect(pm.irect, (255, 255, 255))
            sd = pymupdf.open(); sp = sd.new_page(); sp.insert_image(sp.rect, pixmap=pm)
            rej("scanned / image-only PDF", await up(hA, A1, sd.tobytes()), 422, "no extractable text")
            rej("too many pages (limit 5 in this test)", await up(hA, A1, pdf([f"page {i}" for i in range(6)])), 422, "more than 5 pages")
            padded = doc_pdf() + b"\n%" + b"0" * (1_200_000)
            rej("file over the size limit, seen by the service (1.2 MB > 1 MB)", await up(hA, A1, padded), 413, "1 MB")
            rej("file far over the limit: Content-Length rejected by middleware", await up(hA, A1, b"%PDF-" + b"0" * 3_000_000), 413)
            async def gen():
                yield b'--zz\r\nContent-Disposition: form-data; name="file"; filename="a.pdf"\r\nContent-Type: application/pdf\r\n\r\n%PDF-1.7\n'
                for _ in range(40): yield b"0" * 100_000
                yield b"\r\n--zz--\r\n"
            r = await c.post(f"/courses/{A1}/documents", content=gen(), headers={**hA, "Content-Type": "multipart/form-data; boundary=zz"})
            rej("chunked upload with NO Content-Length: byte counter aborts it", r, 413)
            rej("missing 'file' field", await c.post(f"/courses/{A1}/documents", data={"x": "y"}, headers=hA), 422)
            check("none of the rejected uploads left records", await db["documents"].count_documents({}) == n_docs)
            await consistency("after rejected uploads")

            # ---------- 6. path traversal & filenames ----------
            print("=== 6. filenames are never paths ===")
            cases = {"../../etc/passwd.pdf": "passwd.pdf", "..\\..\\windows\\evil.pdf": "evil.pdf", "a/b/c.pdf": "c.pdf", "/abs/olute.pdf": "olute.pdf", "  spaced   name .pdf": "spaced name .pdf"}
            made = []
            for raw, expect in cases.items():
                r = await up(hA, A2, doc_pdf(), name=raw); j = r.json()
                check(f"filename {raw!r} -> accepted, display name {expect!r}", r.status_code == 202 and j["original_filename"] == expect, (r.status_code, j))
                made.append(j["document_id"]); await poll(hA, A2, j["document_id"], "ready")
            course_dir = UPLOADS / A / A2
            check("stored files are only <document_id>.pdf inside the course directory", {p.name for p in course_dir.glob("*.pdf")} >= {f"{i}.pdf" for i in made} and all(p.parent == course_dir for p in course_dir.rglob("*.pdf")))
            outside = [p for p in _TMP and __import__("pathlib").Path(_TMP).rglob("*") if p.is_file() and UPLOADS not in p.parents and "chroma" not in p.parts]
            check("nothing was created outside the upload and chroma directories", outside == [], outside[:3])
            r = await up(hA, A2, doc_pdf(), name=("x" * 300) + ".pdf"); check("very long filename is shortened for display", r.status_code == 202 and len(r.json()["original_filename"]) <= 150 and r.json()["original_filename"].endswith(".pdf"))
            await poll(hA, A2, r.json()["document_id"], "ready")
            r = await c.post(f"/courses/{A2}/documents", files={"file": ("inj.pdf", doc_pdf(), "application/pdf")}, data={"user_id": B, "course_id": B1}, headers=hA)
            mm = await db["documents"].find_one({"_id": ObjectId(r.json()["document_id"])})
            check("user_id / course_id sent in the request are ignored (taken from token and path)", r.status_code == 202 and mm["user_id"] == A and mm["course_id"] == A2)
            await poll(hA, A2, r.json()["document_id"], "ready")

            # ---------- 7. isolation ----------
            print("=== 7. user-level and course-level isolation ===")
            before = (await db["documents"].count_documents({}), vector_store.get_collection().count(), len(list(UPLOADS.rglob("*.pdf"))))
            r1 = await up(hB, A1, doc_pdf()); r2 = await c.get(f"/courses/{A1}/documents", headers=hB)
            r3 = await c.get(f"/courses/{A1}/documents/{did1}", headers=hB); r4 = await c.delete(f"/courses/{A1}/documents/{did1}", headers=hB)
            check("bob on alice's course: upload/list/get/delete all -> 404 'Course not found'", all(x.status_code == 404 and x.json() == {"detail": "Course not found"} for x in (r1, r2, r3, r4)), [x.status_code for x in (r1, r2, r3, r4)])
            check("...and nothing changed in Mongo, Chroma or on disk", before == (await db["documents"].count_documents({}), vector_store.get_collection().count(), len(list(UPLOADS.rglob("*.pdf")))))
            rx = await c.get(f"/courses/{A2}/documents/{did1}", headers=hA); ry = await c.delete(f"/courses/{A2}/documents/{did1}", headers=hA)
            check("same user, wrong course: document of A1 requested via A2 -> 404, untouched", rx.status_code == ry.status_code == 404 and rx.json() == {"detail": "Document not found"} and chunk_count(A, A1, did1) > 0 and pdf_file(A, A1, did1).exists())
            rb = await up(hB, B1, data1, name="bob-copy.pdf"); bdid = rb.json()["document_id"]; check("bob can upload the byte-identical PDF to his own course", rb.status_code == 202)
            await poll(hB, B1, bdid, "ready")
            check("each user's list shows only their own documents", {d["document_id"] for d in (await c.get(f"/courses/{B1}/documents", headers=hB)).json()} == {bdid} and did1 in {d["document_id"] for d in (await c.get(f"/courses/{A1}/documents", headers=hA)).json()} and bdid not in {d["document_id"] for d in (await c.get(f"/courses/{A1}/documents", headers=hA)).json()})
            res = lambda u, cid: asyncio.to_thread(retrieval.search_chunks, u, cid, "deadlock four conditions", 20)
            ra, rbb, rab, rba = await res(A, A1), await res(B, B1), await res(A, B1), await res(B, A1)
            check("retrieval is scoped: identical content, but alice/A1 sees only alice's chunks and bob/B1 only bob's", {h.document_id for h in ra}.isdisjoint({bdid}) and {h.document_id for h in rbb} == {bdid} and bdid not in {h.document_id for h in ra})
            check("retrieval across users/courses (alice->B1, bob->A1) returns nothing", rab == [] and rba == [])
            nf_doc = await c.get(f"/courses/{A1}/documents/{ObjectId()}", headers=hA); fo_doc = await c.get(f"/courses/{B1}/documents/{bdid}", headers=hA)
            check("non-existent vs foreign document: 404 for foreign course, identical-shape 404 for missing doc", nf_doc.status_code == 404 and fo_doc.status_code == 404 and fo_doc.json() == {"detail": "Course not found"} and nf_doc.json() == {"detail": "Document not found"})
            for label, rr, needle in [("malformed course id", await c.get("/courses/abc/documents", headers=hA), "Invalid course ID"), ("malformed document id", await c.get(f"/courses/{A1}/documents/xyz", headers=hA), "Invalid document ID"), ("malformed document id on delete", await c.delete(f"/courses/{A1}/documents/xyz", headers=hA), "Invalid document ID")]:
                check(f"{label} -> 422", rr.status_code == 422 and needle in rr.text, rr.text)
            lst = (await c.get(f"/courses/{A1}/documents", headers=hA)).json()
            check("list is newest first", [d["created_at"] for d in lst] == sorted([d["created_at"] for d in lst], reverse=True) and len(lst) >= 5)
            check("pagination: limit/skip honoured, bad values -> 422", len((await c.get(f"/courses/{A1}/documents?limit=2", headers=hA)).json()) == 2 and (await c.get(f"/courses/{A1}/documents?skip=1&limit=1", headers=hA)).json()[0]["document_id"] == lst[1]["document_id"] and (await c.get(f"/courses/{A1}/documents?limit=0", headers=hA)).status_code == 422)
            await consistency("after isolation tests")

            # ---------- 8. deletion ----------
            print("=== 8. deletion ===")
            r = await c.delete(f"/courses/{A1}/documents/{did1}", headers=hA)
            check("delete own document -> 204 with empty body", r.status_code == 204 and r.content == b"")
            check("Mongo record, stored PDF and Chroma chunks are all gone", await db["documents"].count_documents({"_id": ObjectId(did1)}) == 0 and not pdf_file(A, A1, did1).exists() and chunk_count(A, A1, did1) == 0)
            check("bob's byte-identical document is untouched", chunk_count(B, B1, bdid) > 0 and pdf_file(B, B1, bdid).exists() and (await c.get(f"/courses/{B1}/documents/{bdid}", headers=hB)).json()["status"] == "ready")
            check("second delete and get -> 404", (await c.delete(f"/courses/{A1}/documents/{did1}", headers=hA)).status_code == 404 and (await c.get(f"/courses/{A1}/documents/{did1}", headers=hA)).status_code == 404)
            r = await up(hA, A1, data1); check("after deleting, the same PDF can be uploaded again", r.status_code == 202); await poll(hA, A1, r.json()["document_id"], "ready")
            ev = threading.Event(); mock_embedder.install(MockSentenceTransformer(block=ev))
            t = asyncio.create_task(up(hA, A1, doc_pdf())); pending = None
            for _ in range(200):
                pending = next((d for d in (await c.get(f"/courses/{A1}/documents", headers=hA)).json() if d["status"] == "processing"), None)
                if pending: break
                await asyncio.sleep(0.05)
            check("a slow job is visible as 'processing'", pending is not None)
            r = await c.delete(f"/courses/{A1}/documents/{pending['document_id']}", headers=hA)
            check("delete while processing -> 409, document untouched", r.status_code == 409 and scan(r) and (await c.get(f"/courses/{A1}/documents/{pending['document_id']}", headers=hA)).json()["status"] == "processing", r.text)
            ev.set(); resp = await t
            check("the upload response itself had said 202 + 'processing'", resp.status_code == 202 and resp.json()["status"] == "processing")
            fin = await poll(hA, A1, pending["document_id"], "ready"); check("job then completes normally", fin["status"] == "ready")
            check("...and can now be deleted", (await c.delete(f"/courses/{A1}/documents/{pending['document_id']}", headers=hA)).status_code == 204)
            mock = mock_embedder.install()

            # ---------- 9. failure handling ----------
            print("=== 9. partial failures ===")
            fdata = doc_pdf(); mock_embedder.install(MockSentenceTransformer(fail=True))
            r = await up(hA, A1, fdata); fid = r.json()["document_id"]; f = await poll(hA, A1, fid, ("failed", "ready"))
            check("embedding failure -> status 'failed' with a safe message", f["status"] == "failed" and f["error"] and scan(await c.get(f"/courses/{A1}/documents/{fid}", headers=hA)) and "mock" not in f["error"].lower(), f)
            check("...no chunks, no stored PDF left behind; record kept so the user sees why", chunk_count(A, A1, fid) == 0 and not pdf_file(A, A1, fid).exists() and (await db["documents"].find_one({"_id": ObjectId(fid)}))["error_code"] == "embedding_unavailable")
            mock = mock_embedder.install(); r = await up(hA, A1, fdata)
            check("a failed upload does not block re-uploading the same file", r.status_code == 202); good = await poll(hA, A1, r.json()["document_id"], "ready"); check("...and it then succeeds", good["status"] == "ready")
            check("failed record can be deleted", (await c.delete(f"/courses/{A1}/documents/{fid}", headers=hA)).status_code == 204 and await db["documents"].count_documents({"_id": ObjectId(fid)}) == 0)
            real_add = vector_store.add_chunks
            def half_write(user_id, course_id, document_id, chunks, embs, cancel_event=None):
                real_add(user_id, course_id, document_id, chunks[:1], embs[:1], cancel_event); raise VectorStoreError("simulated mid-write failure")
            vector_store.add_chunks = half_write
            r = await up(hA, A1, doc_pdf()); pid = r.json()["document_id"]; f = await poll(hA, A1, pid, ("failed", "ready"))
            vector_store.add_chunks = real_add
            check("Chroma failing MID-WRITE -> partial chunks removed, status failed", f["status"] == "failed" and chunk_count(A, A1, pid) == 0 and not pdf_file(A, A1, pid).exists() and (await db["documents"].find_one({"_id": ObjectId(pid)}))["error_code"] == "vector_store_unavailable", f)
            SETTINGS.INGESTION_TIMEOUT_SECONDS = 1; ev = threading.Event(); mock_embedder.install(MockSentenceTransformer(block=ev))
            tt = asyncio.create_task(up(hA, A1, doc_pdf())); await asyncio.sleep(2.5); ev.set(); rr = await tt
            f = await poll(hA, A1, rr.json()["document_id"], ("failed", "ready"), tries=300); SETTINGS.INGESTION_TIMEOUT_SECONDS = 900
            check("a job exceeding the time limit -> failed 'took too long', cleaned up (worker cancelled)", f["status"] == "failed" and "too long" in f["error"] and chunk_count(A, A1, f["document_id"]) == 0 and not pdf_file(A, A1, f["document_id"]).exists(), f)
            mock = mock_embedder.install()
            real_get = vector_store.get_collection
            def down(): raise VectorStoreError("chroma down")
            r = await up(hA, A1, doc_pdf()); sd_id = r.json()["document_id"]; await poll(hA, A1, sd_id, "ready")
            vector_store.get_collection = down
            r = await c.delete(f"/courses/{A1}/documents/{sd_id}", headers=hA)
            check("delete while Chroma is down -> generic 503 (no internals)", r.status_code == 503 and r.json() == {"detail": "Service temporarily unavailable"} and scan(r), r.text)
            check("...record kept as 'deleting' so the delete can be retried", (await c.get(f"/courses/{A1}/documents/{sd_id}", headers=hA)).json()["status"] == "deleting" and pdf_file(A, A1, sd_id).exists())
            vector_store.get_collection = real_get
            r = await c.delete(f"/courses/{A1}/documents/{sd_id}", headers=hA)
            check("retry after recovery -> 204 and everything is gone", r.status_code == 204 and chunk_count(A, A1, sd_id) == 0 and not pdf_file(A, A1, sd_id).exists() and await db["documents"].count_documents({"_id": ObjectId(sd_id)}) == 0)
            await consistency("after failure injection")

            # ---------- 10. course cascade ----------
            print("=== 10. course deletion cascades ===")
            A3 = await mkcourse(hA, "A3"); d3 = []
            for _ in range(2):
                r = await up(hA, A3, doc_pdf()); d3.append(r.json()["document_id"]); await poll(hA, A3, d3[-1], "ready")
            keep_A1 = {d["document_id"] for d in (await c.get(f"/courses/{A1}/documents", headers=hA)).json()}
            r = await c.delete(f"/courses/{A3}", headers=hA)
            check("delete course -> 204", r.status_code == 204)
            check("its documents, PDFs directory and Chroma chunks are gone", await db["documents"].count_documents({"course_id": A3}) == 0 and not (UPLOADS / A / A3).exists() and all(chunk_count(A, A3, i) == 0 for i in d3) and (await c.get(f"/courses/{A3}", headers=hA)).status_code == 404)
            check("other courses (same user and other user) are untouched", keep_A1 == {d["document_id"] for d in (await c.get(f"/courses/{A1}/documents", headers=hA)).json()} and chunk_count(B, B1, bdid) > 0)
            r = await c.delete(f"/courses/{B1}", headers=hA); check("alice cannot delete bob's course (404) and bob's documents survive", r.status_code == 404 and chunk_count(B, B1, bdid) > 0 and (await c.get(f"/courses/{B1}/documents/{bdid}", headers=hB)).status_code == 200)
            A4 = await mkcourse(hA, "A4"); ev = threading.Event(); mock_embedder.install(MockSentenceTransformer(block=ev))
            t = asyncio.create_task(up(hA, A4, doc_pdf())); pend = None
            for _ in range(200):
                row = await db["documents"].find_one({"course_id": A4})
                if row: pend = row; break
                await asyncio.sleep(0.05)
            r = await c.delete(f"/courses/{A4}", headers=hA)
            check("delete course while a document is still processing -> 204", r.status_code == 204 and pend is not None)
            ev.set(); await t; await asyncio.sleep(0.3)
            check("the in-flight job leaves NO orphan chunks, PDF or record behind", chunk_count(A, A4, str(pend["_id"])) == 0 and not pdf_file(A, A4, str(pend["_id"])).exists() and await db["documents"].count_documents({"course_id": A4}) == 0)
            mock = mock_embedder.install()
            A5 = await mkcourse(hA, "A5"); vector_store.get_collection = down
            check("course with no documents can be deleted even if Chroma is down", (await c.delete(f"/courses/{A5}", headers=hA)).status_code == 204)
            A6 = await mkcourse(hA, "A6"); vector_store.get_collection = real_get
            r = await up(hA, A6, doc_pdf()); d6 = r.json()["document_id"]; await poll(hA, A6, d6, "ready"); vector_store.get_collection = down
            r = await c.delete(f"/courses/{A6}", headers=hA)
            check("course WITH documents while Chroma is down -> 503, course kept so it can be retried", r.status_code == 503 and scan(r) and (await c.get(f"/courses/{A6}", headers=hA)).status_code == 200)
            vector_store.get_collection = real_get
            check("retry after recovery -> 204, everything removed", (await c.delete(f"/courses/{A6}", headers=hA)).status_code == 204 and chunk_count(A, A6, d6) == 0 and not (UPLOADS / A / A6).exists())
            await consistency("after cascade tests")

            # ---------- 11. startup recovery ----------
            print("=== 11. startup reconciliation ===")
            r = await up(hA, A1, doc_pdf()); s1 = r.json()["document_id"]; await poll(hA, A1, s1, "ready")
            r = await up(hA, A1, doc_pdf()); s2 = r.json()["document_id"]; await poll(hA, A1, s2, "ready")
            await db["documents"].update_one({"_id": ObjectId(s1)}, {"$set": {"status": "processing", "chunk_count": 0}})
            await db["documents"].update_one({"_id": ObjectId(s2)}, {"$set": {"status": "deleting"}})
            await docsvc.initialize_documents()
            f1 = await db["documents"].find_one({"_id": ObjectId(s1)})
            check("interrupted 'processing' record -> failed 'interrupted', artifacts removed", f1["status"] == "failed" and f1["error_code"] == "interrupted" and chunk_count(A, A1, s1) == 0 and not pdf_file(A, A1, s1).exists(), f1["status"])
            check("half-finished 'deleting' record -> deletion completed", await db["documents"].count_documents({"_id": ObjectId(s2)}) == 0 and chunk_count(A, A1, s2) == 0 and not pdf_file(A, A1, s2).exists())
            check("'interrupted' message is user-readable", (await c.get(f"/courses/{A1}/documents/{s1}", headers=hA)).json()["error"].startswith("Processing was interrupted"))

            # ---------- 12. indexes + regression ----------
            print("=== 12. indexes and existing functionality ===")
            idx = await db["documents"].index_information()
            check("unique partial index on (user, course, sha256) and list index exist", any(v.get("unique") and v["key"] == [("user_id", 1), ("course_id", 1), ("file_sha256", 1)] and "partialFilterExpression" in v for v in idx.values()) and any(v["key"] == [("user_id", 1), ("course_id", 1), ("created_at", -1), ("_id", -1)] for v in idx.values()), list(idx))
            check("health endpoints, /auth/me, course CRUD still work", all([(await c.get(p)).status_code == 200 for p in ["/", "/health", "/health/db"]]) and (await c.get("/auth/me", headers=hA)).json()["id"] == A and (await c.put(f"/courses/{A1}", json={"title": "A1 renamed"}, headers=hA)).status_code == 200)
            check("error bodies seen in this run leaked no paths / internals", all(not any(t in body.lower() for t in LEAK) for _, body in error_bodies), [b for _, b in error_bodies if any(t in b.lower() for t in LEAK)][:2])
            await consistency("final")
            await db.client.drop_database(DB)

asyncio.run(main())
print(f"\n{sum(results)}/{len(results)} passed"); sys.exit(0 if all(results) else 1)
