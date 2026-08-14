"""RAG vector store with a cloud/local switch and hybrid retrieval.

`CLOUD` (config.py) selects the entire stack:

  * True  → CLOUD: HuggingFace serverless embeddings + Pinecone.
  * False → LOCAL: local Ollama embeddings (bge-m3) + on-disk Chroma.

Both go through the same `VectorStore` facade and both run **hybrid retrieval**
when `RAG_HYBRID` is on: a dense semantic search fused with a BM25 keyword
search via Reciprocal Rank Fusion. The keyword index is a tiny per-conversation
JSON of the raw chunks kept next to whichever dense store is active, so keyword
search is completely store-agnostic (Pinecone can't cheaply list a namespace).

Heavy backend deps (chromadb, pinecone, huggingface_hub) are imported lazily
inside the class that needs them, so importing this module stays cheap and only
the *active* pipeline's dependencies are loaded (matches the side-effect-free
import convention used elsewhere in the backend).
"""
import json
import os
import re
import threading
import time

from langchain_core.embeddings import Embeddings
from ollama import Client

from backend.config import (
    CLOUD,
    RAG_HYBRID,
    PINECONE_API_KEY,
    PINECONE_INDEX,
    OLLAMA_HOST,
    OLLAMA_HEADERS,
    HF_TOKEN,
    HF_EMBED_MODEL,
    HF_EMBED_BATCH_SIZE,
    HF_EMBED_MAX_RETRIES,
    LOCAL_EMBED_MODEL,
    CHROMA_DIR,
    KEYWORD_INDEX_DIR,
)
from backend.utils.logger import logger


# ── Embeddings ──────────────────────────────────────────────────────────────

class OllamaEmbeddings(Embeddings):
    """LangChain embeddings backed by a LOCAL Ollama model (default bge-m3).

    Used by the local RAG pipeline. Talks to the same daemon as LLMClient
    (host/auth from config.py, BUG-20). The model must be pulled on that host
    (`ollama pull bge-m3`). bge-m3 is 1024-dim.
    """

    def __init__(self, model=None, host=None):
        self._client = Client(host=host or OLLAMA_HOST, headers=OLLAMA_HEADERS)
        self._model = model or LOCAL_EMBED_MODEL

    def embed_documents(self, texts):
        resp = self._client.embed(model=self._model, input=list(texts))
        return [list(vec) for vec in resp["embeddings"]]

    def embed_query(self, text):
        resp = self._client.embed(model=self._model, input=text)
        return list(resp["embeddings"][0])


class HFInferenceEmbeddings(Embeddings):
    """LangChain embeddings backed by HuggingFace serverless Inference.

    Used by the cloud RAG pipeline. Calls
    `huggingface_hub.InferenceClient.feature_extraction` — the current
    router-based path (the old ``api-inference.huggingface.co`` host no longer
    resolves). The default model ``BAAI/bge-m3`` is 1024-dim, matching both the
    Pinecone index and the local Ollama bge-m3 model. (The requested
    ``Qwen/Qwen3-Embedding-0.6B`` is not served on the free serverless API — it
    returns 404 for feature-extraction — so bge-m3 is the working default; see
    HF_EMBED_MODEL in config.py.)

    Documents are embedded in **batches** (`HF_EMBED_BATCH_SIZE`, one HTTP call
    per batch) so a large upload doesn't fire hundreds of serial requests at the
    free-tier rate limit — a ~250-chunk doc goes from ~90s of serial calls to
    ~9s. Transient errors (429/503/timeouts) are retried with exponential
    backoff, then a failing batch is retried item-by-item. Per-chunk size is a
    non-issue: bge-m3 truncates internally, and chunks are ~1000 chars anyway.
    """

    def __init__(self, model=None, token=None, batch_size=None, max_retries=None):
        from huggingface_hub import InferenceClient

        self._model = model or HF_EMBED_MODEL
        self._client = InferenceClient(token=token or HF_TOKEN)
        self._batch = batch_size or HF_EMBED_BATCH_SIZE
        self._max_retries = max_retries or HF_EMBED_MAX_RETRIES

    def _call(self, payload):
        """Call HF feature-extraction, retrying transient failures (429 rate
        limit, 503 model-loading, timeouts) with exponential backoff."""
        last = None
        for attempt in range(self._max_retries):
            try:
                return self._client.feature_extraction(payload, model=self._model)
            except Exception as e:  # huggingface_hub raises various HTTP errors
                last = e
                if attempt == self._max_retries - 1:
                    break
                wait = 2 ** attempt
                logger.warning(
                    f"[RAG] HF embedding call failed ({type(e).__name__}: "
                    f"{str(e)[:120]}); retry {attempt + 1}/{self._max_retries} in {wait}s"
                )
                time.sleep(wait)
        raise last

    @staticmethod
    def _normalize(raw, expected_n):
        import numpy as np

        arr = np.asarray(raw, dtype="float32")
        if arr.ndim == 1:          # single vector for a 1-item request -> (1, dim)
            arr = arr[None, :]
        elif arr.ndim == 3:        # token-level (N, seq, dim) -> mean-pool to (N, dim)
            arr = arr.mean(axis=1)
        if arr.shape[0] != expected_n:
            raise ValueError(f"HF returned {arr.shape[0]} vectors for {expected_n} inputs")
        return [row.tolist() for row in arr]

    def _embed_batch(self, batch):
        """Embed one batch (a list of texts) in a single HTTP call. On failure,
        fall back to item-by-item so one bad batch can't fail the whole doc."""
        try:
            return self._normalize(self._call(batch), len(batch))
        except Exception:
            if len(batch) == 1:
                raise
            logger.warning("[RAG] HF batch embed failed; retrying items individually")
            out = []
            for text in batch:
                out.extend(self._embed_batch([text]))
            return out

    def embed_documents(self, texts):
        texts = list(texts)
        out = []
        # Batch to keep a big document from firing hundreds of serial requests.
        for i in range(0, len(texts), self._batch):
            out.extend(self._embed_batch(texts[i:i + self._batch]))
        return out

    def embed_query(self, text):
        return self._embed_batch([text])[0]


_embeddings_cache = {}


def _get_local_embeddings():
    if "local" not in _embeddings_cache:
        logger.info(f"[RAG] loading local Ollama embeddings: {LOCAL_EMBED_MODEL}")
        _embeddings_cache["local"] = OllamaEmbeddings()
    return _embeddings_cache["local"]


def _get_cloud_embeddings():
    if "cloud" not in _embeddings_cache:
        logger.info(f"[RAG] loading HF serverless embeddings: {HF_EMBED_MODEL}")
        _embeddings_cache["cloud"] = HFInferenceEmbeddings()
    return _embeddings_cache["cloud"]


# ── Keyword (BM25) index ──────────────────────────────────────────────────────

_WORD_RE = re.compile(r"\w+")


def _tokenize(text):
    return _WORD_RE.findall(text.lower())


class KeywordIndex:
    """Per-conversation BM25 keyword index over the raw chunks.

    Persisted as one small JSON file per conversation, independent of the dense
    store. A conversation's chunk set is small, so the BM25 model is rebuilt in
    memory per query rather than persisted.
    """

    def __init__(self):
        KEYWORD_INDEX_DIR.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, conversation_id):
        return KEYWORD_INDEX_DIR / f"conv_{conversation_id}.json"

    def add(self, chunks, conversation_id):
        with self._lock:
            path = self._path(conversation_id)
            existing = []
            if path.exists():
                existing = json.loads(path.read_text(encoding="utf-8"))
            existing.extend(chunks)
            path.write_text(json.dumps(existing), encoding="utf-8")

    def search(self, query, conversation_id, top_k):
        path = self._path(conversation_id)
        if not path.exists():
            return []
        chunks = json.loads(path.read_text(encoding="utf-8"))
        if not chunks:
            return []

        from rank_bm25 import BM25Okapi

        bm25 = BM25Okapi([_tokenize(c) for c in chunks])
        scores = bm25.get_scores(_tokenize(query))
        ranked = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)
        out = []
        for i in ranked[:top_k]:
            if scores[i] <= 0:  # no keyword overlap — not a real match
                break
            out.append({"chunk": chunks[i], "bm25": float(scores[i])})
        return out

    def delete(self, conversation_id):
        self._path(conversation_id).unlink(missing_ok=True)


# ── Dense backends ────────────────────────────────────────────────────────────

class _PineconeBackend:
    """Cloud dense store. Returns cosine similarity (higher = better)."""

    def __init__(self, embeddings):
        from langchain_pinecone import PineconeVectorStore

        self._PVS = PineconeVectorStore
        self._embeddings = embeddings
        self._index = PINECONE_INDEX
        if PINECONE_API_KEY:
            os.environ["PINECONE_API_KEY"] = PINECONE_API_KEY

    @staticmethod
    def _ns(conversation_id):
        return f"conv_{conversation_id}"

    def add_chunks(self, chunks, conversation_id):
        self._PVS.from_texts(
            texts=chunks,
            embedding=self._embeddings,
            index_name=self._index,
            namespace=self._ns(conversation_id),
        )

    def search(self, query, conversation_id, top_k):
        vs = self._PVS(
            index_name=self._index,
            embedding=self._embeddings,
            namespace=self._ns(conversation_id),
        )
        results = vs.similarity_search_with_score(query, k=top_k)
        return [{"chunk": doc.page_content, "score": float(score)} for doc, score in results]

    def delete(self, conversation_id):
        from pinecone import Pinecone

        pc = Pinecone(api_key=PINECONE_API_KEY)
        pc.Index(self._index).delete(delete_all=True, namespace=self._ns(conversation_id))


class _ChromaBackend:
    """Local dense store. Uses a per-conversation collection in an on-disk
    Chroma DB. Returns normalized cosine relevance in [0, 1] (higher = better),
    matching the Pinecone path and the RAG_SCORE_THRESHOLD semantics."""

    def __init__(self, embeddings):
        from langchain_chroma import Chroma

        self._Chroma = Chroma
        self._embeddings = embeddings
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        self._dir = str(CHROMA_DIR)

    @staticmethod
    def _collection(conversation_id):
        return f"conv_{conversation_id}"

    def _store(self, conversation_id):
        return self._Chroma(
            collection_name=self._collection(conversation_id),
            embedding_function=self._embeddings,
            persist_directory=self._dir,
            # cosine space so relevance scores line up with the Pinecone path
            collection_metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(self, chunks, conversation_id):
        self._store(conversation_id).add_texts(chunks)

    def search(self, query, conversation_id, top_k):
        results = self._store(conversation_id).similarity_search_with_relevance_scores(
            query, k=top_k
        )
        return [{"chunk": doc.page_content, "score": float(score)} for doc, score in results]

    def delete(self, conversation_id):
        self._store(conversation_id).delete_collection()


# ── Facade ────────────────────────────────────────────────────────────────────

class VectorStore:
    """Single entry point used by app.py. Dispatches to the cloud or local
    dense backend based on CLOUD and fuses in BM25 keyword hits (RAG_HYBRID).

    Public interface is unchanged from the original Pinecone-only version:
    `add_chunks`, `search`, `delete_namespace` (plus no-op `load`/`save`).
    """

    def __init__(self):
        self._keyword = KeywordIndex()
        if CLOUD:
            self._dense = _PineconeBackend(_get_cloud_embeddings())
            self._backend_name = "cloud(hf+pinecone)"
        else:
            self._dense = _ChromaBackend(_get_local_embeddings())
            self._backend_name = "local(ollama+chroma)"

    def add_chunks(self, chunks, conversation_id: int):
        """Embed + index chunks into the active dense store (and the BM25 index)."""
        if not chunks:
            return
        self._dense.add_chunks(chunks, conversation_id)
        if RAG_HYBRID:
            self._keyword.add(chunks, conversation_id)

    def search(self, query: str, conversation_id: int, top_k: int = 3):
        """Hybrid retrieval. Returns a list of dicts:
            {"chunk": str, "score": float | None, "keyword_hit": bool}
        `score` is the dense cosine similarity (None for a keyword-only hit);
        `keyword_hit` flags a BM25 match so app.py can let strong keyword
        matches bypass the semantic relevance threshold."""
        if not RAG_HYBRID:
            dense = self._dense.search(query, conversation_id, top_k)
            return [
                {"chunk": r["chunk"], "score": r["score"], "keyword_hit": False}
                for r in dense
            ]

        # Pull a wider pool from each retriever, then fuse and trim to top_k.
        pool = max(top_k, 10)
        dense = self._dense.search(query, conversation_id, pool)
        keyword = self._keyword.search(query, conversation_id, pool)
        return self._fuse(dense, keyword, top_k)

    @staticmethod
    def _fuse(dense, keyword, top_k, k: int = 60):
        """Reciprocal Rank Fusion of the dense and keyword rankings, keyed by
        chunk text. Each surviving entry keeps its dense cosine `score` (for the
        threshold in app.py) and a `keyword_hit` flag."""
        entries = {}

        def _entry(chunk):
            if chunk not in entries:
                entries[chunk] = {
                    "chunk": chunk,
                    "score": None,
                    "keyword_hit": False,
                    "rrf": 0.0,
                }
            return entries[chunk]

        for rank, r in enumerate(dense):
            e = _entry(r["chunk"])
            e["score"] = r["score"]
            e["rrf"] += 1.0 / (k + rank + 1)

        for rank, r in enumerate(keyword):
            e = _entry(r["chunk"])
            e["keyword_hit"] = True
            e["rrf"] += 1.0 / (k + rank + 1)

        ranked = sorted(entries.values(), key=lambda e: e["rrf"], reverse=True)
        return [
            {"chunk": e["chunk"], "score": e["score"], "keyword_hit": e["keyword_hit"]}
            for e in ranked[:top_k]
        ]

    def delete_namespace(self, conversation_id: int):
        """Delete a conversation's vectors from the active dense store and its
        keyword index."""
        try:
            self._dense.delete(conversation_id)
            logger.info(
                f"[RAG] deleted dense store for conv {conversation_id} "
                f"({self._backend_name})"
            )
        except Exception as e:
            # Deletion is idempotent: a namespace/collection that was never
            # created (e.g. an upload that failed before indexing) is not an
            # error worth shouting about.
            msg = str(e).lower()
            if "not found" in msg or "404" in msg or "does not exist" in msg:
                logger.info(
                    f"[RAG] dense store for conv {conversation_id} already absent"
                )
            else:
                logger.error(
                    f"[RAG] failed to delete dense store for conv {conversation_id}: {e}"
                )
        self._keyword.delete(conversation_id)

    # Retained for interface compatibility — both stores persist themselves.
    def load(self, file_path):
        pass

    def save(self, file_path):
        pass
