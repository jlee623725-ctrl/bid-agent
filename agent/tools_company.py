"""Company-related tools: search, profile, competitor analysis."""

import logging
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "bid_agent.db"


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _parse_capital(raw: Any) -> float:
    """Parse registered capital like '9,715.96万(元)' → 97159600.0."""
    if raw is None:
        return 0.0
    s = str(raw).strip().replace(",", "").replace("，", "")
    s = re.sub(r"[()（）]", "", s)
    try:
        num = float(re.findall(r"[\d.]+", s)[0])
    except (IndexError, ValueError):
        return 0.0
    if "亿" in s:
        num *= 100_000_000
    elif "万" in s or "萬" in s:
        num *= 10_000
    return num


# ── Tool implementations ──────────────────────────────────────────────────

def search_companies(
    city: str = None,
    industry: str = None,
    min_capital: float = 0,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Multi-condition company search from qcc_companies table."""
    conn = _get_conn()
    try:
        conditions = []
        params: List[Any] = []

        if city:
            conditions.append("city LIKE ?")
            params.append(f"%{city}%")
        if industry:
            conditions.append("industry LIKE ?")
            params.append(f"%{industry}%")

        where = " AND ".join(conditions) if conditions else "1=1"
        sql = f"""
            SELECT company_name, legal_representative, registered_capital,
                   establishment_date, province, city, district,
                   industry, company_type, business_scope
            FROM qcc_companies
            WHERE {where}
            LIMIT ?
        """
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()

        results = []
        for r in rows:
            d = dict(r)
            cap = _parse_capital(d.get("registered_capital"))
            d["registered_capital_value"] = cap
            if cap < min_capital:
                continue
            results.append(d)

        logger.info(
            "search_companies(city=%r, industry=%r, min_capital=%s) → %d results",
            city, industry, min_capital, len(results),
        )
        return results
    finally:
        conn.close()


def get_company_profile(company_name: str) -> Dict[str, Any]:
    """Company panorama: basic info + bidding records + peer count."""
    conn = _get_conn()
    try:
        # Basic info
        row = conn.execute(
            """
            SELECT * FROM qcc_companies
            WHERE company_name LIKE ?
            LIMIT 1
            """,
            (f"%{company_name}%",),
        ).fetchone()

        if row is None:
            logger.warning("get_company_profile(%r) → not found", company_name)
            return {"error": f"Company '{company_name}' not found"}

        profile = dict(row)
        profile["registered_capital_value"] = _parse_capital(
            profile.get("registered_capital")
        )

        # Bidding records — match company name against successful_bidder
        bids = conn.execute(
            """
            SELECT notice_id, notice_type, awarded_amount, tendering_entity,
                   notice_content
            FROM bidding_notices
            WHERE successful_bidder LIKE ?
            LIMIT 20
            """,
            (f"%{company_name}%",),
        ).fetchall()
        profile["bidding_records"] = [dict(b) for b in bids]

        # Peer count — same industry
        industry = (profile.get("industry") or "").strip()
        peer_count = 0
        if industry:
            peer_count = conn.execute(
                "SELECT COUNT(*) FROM qcc_companies WHERE industry LIKE ?",
                (f"%{industry}%",),
            ).fetchone()[0]
        profile["peer_count"] = peer_count

        logger.info(
            "get_company_profile(%r) → %d bidding records, %d peers",
            company_name, len(bids), peer_count,
        )
        return profile
    finally:
        conn.close()


def find_competitors(company_name: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Find competitors in same region + industry, ranked by registered capital."""
    conn = _get_conn()
    try:
        target = conn.execute(
            """
            SELECT city, district, industry FROM qcc_companies
            WHERE company_name LIKE ?
            LIMIT 1
            """,
            (f"%{company_name}%",),
        ).fetchone()

        if target is None:
            logger.warning("find_competitors(%r) → target not found", company_name)
            return [{"error": f"Company '{company_name}' not found"}]

        city = (target["city"] or "").strip()
        industry = (target["industry"] or "").strip()

        rows = conn.execute(
            """
            SELECT company_name, legal_representative, registered_capital,
                   establishment_date, province, city, district,
                   industry, company_type
            FROM qcc_companies
            WHERE city LIKE ? AND industry LIKE ?
              AND company_name NOT LIKE ?
            LIMIT 200
            """,
            (f"%{city}%", f"%{industry}%", f"%{company_name}%"),
        ).fetchall()

        results = []
        for r in rows:
            d = dict(r)
            d["registered_capital_value"] = _parse_capital(d.get("registered_capital"))
            results.append(d)

        results.sort(key=lambda x: x["registered_capital_value"], reverse=True)
        top = results[:limit]

        logger.info(
            "find_competitors(%r) → %d total, top %d returned",
            company_name, len(results), len(top),
        )
        return top
    finally:
        conn.close()


# ── OpenAI function calling schema ────────────────────────────────────────

tools_schema = [
    {
        "type": "function",
        "function": {
            "name": "search_companies",
            "description": "多条件筛选企业：支持按城市、行业、最低注册资本查询，返回企业列表",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名称，模糊匹配",
                    },
                    "industry": {
                        "type": "string",
                        "description": "行业关键词，如'房地产'、'信息技术'",
                    },
                    "min_capital": {
                        "type": "number",
                        "description": "最低注册资本（元），默认 0",
                        "default": 0,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回条数上限，默认 20",
                        "default": 20,
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_company_profile",
            "description": "企业全景画像：包含基本信息、历史中标记录、同行业企业数量",
            "parameters": {
                "type": "object",
                "properties": {
                    "company_name": {
                        "type": "string",
                        "description": "企业名称（支持模糊匹配）",
                    },
                },
                "required": ["company_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_competitors",
            "description": "查找目标企业在同地区同行业的竞争对手，按注册资本降序排列",
            "parameters": {
                "type": "object",
                "properties": {
                    "company_name": {
                        "type": "string",
                        "description": "目标企业名称",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回数量，默认 10",
                        "default": 10,
                    },
                },
                "required": ["company_name"],
            },
        },
    },
]
