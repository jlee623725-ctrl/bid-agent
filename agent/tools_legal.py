"""Legal tools: search laws and retrieve specific articles."""

import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

from agent.vector_store import VectorStore

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "bid_agent.db"

_vec_store: VectorStore = None


def _get_vec_store() -> VectorStore:
    global _vec_store
    if _vec_store is None:
        _vec_store = VectorStore()
    return _vec_store


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


# ── Tool implementations ──────────────────────────────────────────────────

def semantic_search_laws(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """Semantic (TF-IDF) search across laws and policy documents."""
    try:
        results = _get_vec_store().search(query, top_k=top_k)
        logger.info("semantic_search_laws(query=%r) → %d results", query[:50], len(results))
        return results
    except FileNotFoundError as e:
        logger.warning("Vector index not available: %s", e)
        return [{"error": "语义搜索索引未构建，请先运行 scripts/build_index.py"}]


def search_laws(keyword: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Full-text search across laws table by content and title."""
    conn = _get_conn()
    try:
        pattern = f"%{keyword}%"
        rows = conn.execute(
            """
            SELECT document_type, document_title, chapter_title,
                   section_title, article_number, content
            FROM laws
            WHERE content LIKE ? OR document_title LIKE ?
            LIMIT ?
            """,
            (pattern, pattern, limit),
        ).fetchall()
        logger.info("search_laws(keyword=%r, limit=%d) → %d results", keyword, limit, len(rows))
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_article(law_title: str, article_number: str) -> Dict[str, Any]:
    """Lookup a specific article within a law. Tries exact match first, then fuzzy."""
    conn = _get_conn()
    try:
        # Try exact match first
        row = conn.execute(
            """
            SELECT document_type, document_title, chapter_title,
                   section_title, article_number, content
            FROM laws
            WHERE document_title LIKE ? AND article_number = ?
            LIMIT 1
            """,
            (f"%{law_title}%", str(article_number)),
        ).fetchone()

        if row is None:
            # Fuzzy match: article_number may contain the number as substring
            row = conn.execute(
                """
                SELECT document_type, document_title, chapter_title,
                       section_title, article_number, content
                FROM laws
                WHERE document_title LIKE ? AND article_number LIKE ?
                LIMIT 1
                """,
                (f"%{law_title}%", f"%{article_number}%"),
            ).fetchone()

        if row is None:
            # Last resort: return any article from this law
            row = conn.execute(
                """
                SELECT document_type, document_title, chapter_title,
                       section_title, article_number, content
                FROM laws
                WHERE document_title LIKE ?
                LIMIT 1
                """,
                (f"%{law_title}%",),
            ).fetchone()

        if row is None:
            logger.warning(
                "get_article(title=%r, article=%r) → not found",
                law_title, article_number,
            )
            return {"error": f"Article '{article_number}' not found in '{law_title}'"}

        logger.info(
            "get_article(title=%r, article=%r) → OK",
            law_title, article_number,
        )
        return dict(row)
    finally:
        conn.close()


# ── OpenAI function calling schema ────────────────────────────────────────

tools_schema = [
    {
        "type": "function",
        "function": {
            "name": "semantic_search_laws",
            "description": "语义搜索法律法规和政策文档，基于TF-IDF理解查询意图，比关键词匹配更智能。适合自然语言问题如'投标保证金有什么规定'",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "自然语言查询，如'政府采购中的中小企业优惠政策'",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "返回条数，默认 5",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_laws",
            "description": "全文搜索法律法规，根据关键词在法条内容和标题中模糊匹配，返回匹配的法律条文摘要",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "搜索关键词，如'投标保证金'、'政府采购'",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回条数上限，默认 5",
                        "default": 5,
                    },
                },
                "required": ["keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_article",
            "description": "精确查询某部法律的某一条款原文",
            "parameters": {
                "type": "object",
                "properties": {
                    "law_title": {
                        "type": "string",
                        "description": "法律名称，如'招标投标法'",
                    },
                    "article_number": {
                        "type": "string",
                        "description": "条款编号",
                    },
                },
                "required": ["law_title", "article_number"],
            },
        },
    },
]
