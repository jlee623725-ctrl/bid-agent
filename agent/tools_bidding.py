"""Bidding-related tools: search notices, query trends, get notice detail."""

import logging
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "bid_agent.db"


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _parse_amount(raw: Any) -> float:
    """Convert Chinese-format amount strings like '9,715.96万(元)' to float."""
    if raw is None:
        return 0.0
    s = str(raw).strip().replace(",", "").replace("，", "")
    s = re.sub(r"[一-鿿()（）]", "", s)
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


# ── Tool implementations ──────────────────────────────────────────────────

def search_notices(keyword: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Search bidding notices by keyword across multiple columns."""
    conn = _get_conn()
    try:
        pattern = f"%{keyword}%"
        rows = conn.execute(
            """
            SELECT notice_id, notice_type, tender_number, successful_bidder,
                   awarded_amount, tendering_entity, tendering_address,
                   notice_content
            FROM bidding_notices
            WHERE notice_content LIKE ? OR notice_type LIKE ?
               OR tender_number LIKE ? OR successful_bidder LIKE ?
               OR tendering_entity LIKE ?
            LIMIT ?
            """,
            (pattern, pattern, pattern, pattern, pattern, limit),
        ).fetchall()
        logger.info("search_notices(keyword=%r, limit=%d) → %d results", keyword, limit, len(rows))
        return [dict(r) for r in rows]
    finally:
        conn.close()


def query_trends(industry: str, months: int = 6) -> Dict[str, Any]:
    """Aggregate bidding amounts and counts for an industry over recent N months."""
    conn = _get_conn()
    try:
        cutoff = datetime.now() - timedelta(days=months * 30)
        pattern = f"%{industry}%"

        rows = conn.execute(
            """
            SELECT bidding, bid_amount, data, content
            FROM bidding_transactions
            WHERE (content LIKE ? OR type LIKE ?)
            LIMIT 2000
            """,
            (pattern, pattern),
        ).fetchall()

        total_amount = 0.0
        winners: Dict[str, float] = {}
        count = 0

        for r in rows:
            date_str = r["data"]
            if date_str:
                try:
                    d = datetime.strptime(str(date_str).strip(), "%Y/%m/%d")
                    if d < cutoff:
                        continue
                except ValueError:
                    pass  # include if date can't be parsed

            amt = _parse_amount(r["bid_amount"])
            total_amount += amt
            count += 1

            winner = (r["bidding"] or "").strip()
            if winner:
                winners[winner] = winners.get(winner, 0) + amt

        top_winners = sorted(winners.items(), key=lambda x: x[1], reverse=True)[:5]
        logger.info(
            "query_trends(industry=%r, months=%d) → %d records, total=%.2f",
            industry, months, count, total_amount,
        )
        return {
            "total_amount": round(total_amount, 2),
            "count": count,
            "top_winners": [{"name": n, "amount": round(a, 2)} for n, a in top_winners],
        }
    finally:
        conn.close()


def get_notice_detail(notice_id: int) -> Dict[str, Any]:
    """Return full detail of a single bidding notice."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM bidding_notices WHERE notice_id = ?", (str(notice_id),)
        ).fetchone()
        if row is None:
            logger.warning("get_notice_detail(notice_id=%d) → not found", notice_id)
            return {"error": f"Notice {notice_id} not found"}
        logger.info("get_notice_detail(notice_id=%d) → OK", notice_id)
        return dict(row)
    finally:
        conn.close()


# ── OpenAI function calling schema ────────────────────────────────────────

tools_schema = [
    {
        "type": "function",
        "function": {
            "name": "search_notices",
            "description": "搜索招标公告，根据关键词在公告内容、公告类型、招标编号、中标人、招标单位中模糊匹配",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "搜索关键词",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回条数上限，默认 10",
                        "default": 10,
                    },
                },
                "required": ["keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_trends",
            "description": "统计某行业近N个月的中标金额总和、中标数量及中标金额前五的企业",
            "parameters": {
                "type": "object",
                "properties": {
                    "industry": {
                        "type": "string",
                        "description": "行业关键词，如'房地产'、'信息技术'、'建筑'",
                    },
                    "months": {
                        "type": "integer",
                        "description": "统计近几个月的趋势，默认 6",
                        "default": 6,
                    },
                },
                "required": ["industry"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_notice_detail",
            "description": "根据公告 ID 获取完整公告内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "notice_id": {
                        "type": "integer",
                        "description": "招标公告 ID",
                    },
                },
                "required": ["notice_id"],
            },
        },
    },
]
