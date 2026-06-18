"""Vector store with TF-IDF + cosine similarity for semantic retrieval.

Uses sklearn TfidfVectorizer (offline, no GPU/network required).
Interface is designed so neural embeddings can be swapped in later.
"""

import json
import logging
import pickle
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
INDEX_DIR = ROOT / "data" / "vector_index"


class VectorStore:
    """TF-IDF vector store for Chinese legal/policy document retrieval.

    Stores: tfidf_vectorizer.pkl, tfidf_matrix.npy, metadata.json
    """

    def __init__(self, index_dir: Path = INDEX_DIR) -> None:
        self.index_dir = index_dir
        self._vectorizer: TfidfVectorizer = None
        self._matrix: np.ndarray = None
        self._metadata: List[Dict[str, Any]] = []
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        vec_path = self.index_dir / "tfidf_vectorizer.pkl"
        mat_path = self.index_dir / "tfidf_matrix.npy"
        meta_path = self.index_dir / "laws_policy_meta.json"

        if not (vec_path.exists() and mat_path.exists() and meta_path.exists()):
            raise FileNotFoundError(
                f"Index not found at {self.index_dir}. Run scripts/build_index.py first."
            )

        with open(vec_path, "rb") as f:
            self._vectorizer = pickle.load(f)
        self._matrix = np.load(mat_path)
        self._metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        self._loaded = True
        logger.info(
            "Loaded TF-IDF index: %d docs, %d features",
            self._matrix.shape[0], self._matrix.shape[1],
        )

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Semantic (TF-IDF cosine) search returning top_k results."""
        self._ensure_loaded()

        q_vec = self._vectorizer.transform([query])
        scores = cosine_similarity(q_vec, self._matrix)[0]
        top_indices = np.argsort(scores)[::-1][:top_k]

        results: List[Dict[str, Any]] = []
        for idx in top_indices:
            if scores[idx] <= 0:
                continue
            meta = dict(self._metadata[idx])
            meta["_score"] = round(float(scores[idx]), 4)
            results.append(meta)

        logger.info(
            "Vector search(%r, top_k=%d) → %d results",
            query[:50], top_k, len(results),
        )
        return results

    # ── Builder (static) ───────────────────────────────────────────────

    @staticmethod
    def build_from_db(
        db_path: Path,
        output_dir: Path,
    ) -> "VectorStore":
        """Build TF-IDF index from laws + policies in SQLite."""
        output_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Building TF-IDF index from %s", db_path)

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        documents: List[Dict[str, Any]] = []

        # Laws
        for row in conn.execute(
            "SELECT document_type, document_title, chapter_title, "
            "section_title, article_number, content FROM laws"
        ):
            text = " ".join(
                filter(None, [
                    row["document_title"] or "",
                    row["chapter_title"] or "",
                    row["article_number"] or "",
                    (row["content"] or "")[:2000],
                ])
            )
            if len(text.strip()) > 10:
                documents.append({
                    "source": "laws",
                    "document_title": row["document_title"],
                    "document_type": row["document_type"],
                    "article_number": row["article_number"],
                    "text": text,
                })

        # Policies
        for table in ["t_policy", "policy"]:
            try:
                for row in conn.execute(f'SELECT * FROM "{table}"'):
                    title = (
                        row["title"]
                        if "title" in row.keys()
                        else row.get("policy_title", "")
                    )
                    content = (
                        row["text"]
                        if "text" in row.keys()
                        else row.get("content", "")
                    )
                    text = f"{title or ''} {(content or '')[:2000]}"
                    if len(text.strip()) > 10:
                        documents.append({
                            "source": table,
                            "title": title,
                            "text": text,
                        })
            except Exception:
                pass

        conn.close()
        logger.info("Collected %d documents", len(documents))

        # Build TF-IDF
        vectorizer = TfidfVectorizer(
            max_features=5000,
            ngram_range=(1, 2),
            analyzer="char_wb",
        )
        texts = [d["text"] for d in documents]
        matrix = vectorizer.fit_transform(texts)
        logger.info(
            "TF-IDF matrix: %d docs × %d features, nnz=%d",
            matrix.shape[0], matrix.shape[1], matrix.nnz,
        )

        # Persist
        with open(output_dir / "tfidf_vectorizer.pkl", "wb") as f:
            pickle.dump(vectorizer, f)
        np.save(output_dir / "tfidf_matrix.npy", matrix.toarray())
        (output_dir / "laws_policy_meta.json").write_text(
            json.dumps(documents, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("Index saved to %s", output_dir)

        store = VectorStore(index_dir=output_dir)
        store._vectorizer = vectorizer
        store._matrix = matrix.toarray()
        store._metadata = documents
        store._loaded = True
        return store
