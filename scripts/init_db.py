"""
Initialize SQLite database from CSV files in data/ directory.

Usage: python scripts/init_db.py
Output: data/bid_agent.db
"""

import logging
import os
import re
import sqlite3
from pathlib import Path
from typing import Dict, List, Set

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
DB_PATH = DATA_DIR / "bid_agent.db"

ENCODINGS_TO_TRY = ["utf-8", "gbk", "gb18030", "gb2312", "latin-1"]

# ── Column name standardization ──────────────────────────────────────────

CN_COLUMN_MAP: Dict[str, str] = {
    # Company / enterprise fields
    "企业名称": "company_name",
    "法定代表人": "legal_representative",
    "注册资本": "registered_capital",
    "成立日期": "establishment_date",
    "核准日期": "approval_date",
    "营业期限": "business_term",
    "所属省份": "province",
    "所属城市": "city",
    "所属区县": "district",
    "统一社会信用代码": "unified_social_credit_code",
    "参保人数": "insured_count",
    "企业类型": "company_type",
    "所属行业": "industry",
    "注册地址": "registered_address",
    "经营范围": "business_scope",
    # Bidding / tender fields
    "招标人": "tendering_entity",
    "中标人": "successful_bidder",
    "中标金额": "awarded_amount",
    "项目编号": "project_number",
    "项目名称": "project_name",
    "公告类型": "notice_type",
    "招标编号": "tender_number",
    "招标内容": "notice_content",
    "招标单位": "tendering_entity",
    "采购人": "purchaser",
    "代理机构": "agency",
    "开标时间": "bid_opening_time",
    "资格审查": "qualification_review",
    "资质要求": "qualification_requirements",
    "评标办法": "evaluation_method",
    "联系人": "contact_person",
    "联系电话": "contact_phone",
    # Policy / document fields
    "政策标题": "policy_title",
    "发布日期": "publish_date",
    "发布时间": "release_time",
    "文档标题": "document_title",
    "文档类型": "document_type",
    "来源": "source",
    "来源网址": "source_url",
    "内容": "content",
    "省份": "province",
    "城市": "city",
    "区县": "district",
    "地区": "region",
    "行业": "industry",
    "状态": "status",
    "类型": "type",
    "标题": "title",
    "链接": "link",
    "数据": "data",
}

# ── Chinese filename → English table name ────────────────────────────────

FILENAME_MAP: Dict[str, str] = {
    "招投标交易": "bidding_transactions",
}


# ── Helpers ───────────────────────────────────────────────────────────────

def sanitize_table_name(name: str) -> str:
    """Convert filename stem to a safe SQLite table name."""
    name = FILENAME_MAP.get(name, name)
    name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    name = re.sub(r"_+", "_", name).strip("_").lower()
    if name[0].isdigit():
        name = "t_" + name
    return name


def standardize_columns(columns: List[str]) -> List[str]:
    """Map Chinese column names to English; ensure safe SQL identifiers."""
    result: List[str] = []
    seen: Set[str] = set()
    for col in columns:
        col = col.strip()
        # Replace spaces/hyphens with underscores for multi-word English names
        english = CN_COLUMN_MAP.get(col, col)
        english = re.sub(r"[^a-zA-Z0-9_]", "_", english)
        english = re.sub(r"_+", "_", english).strip("_").lower()
        if not english or english[0].isdigit():
            english = "col_" + english if col else f"col_{len(result)}"
        # Deduplicate
        original = english
        n = 1
        while english in seen:
            english = f"{original}_{n}"
            n += 1
        seen.add(english)
        result.append(english)
    return result


def detect_encoding(filepath: Path) -> str:
    """Try known encodings; fall back to the first that works."""
    for enc in ENCODINGS_TO_TRY:
        try:
            with open(filepath, encoding=enc) as f:
                f.readline()
            return enc
        except (UnicodeDecodeError, UnicodeError):
            continue
    return "utf-8"


def infer_sqlite_type(series: pd.Series) -> str:
    """Infer the best SQLite type for a pandas Series."""
    if pd.api.types.is_integer_dtype(series):
        return "INTEGER"
    if pd.api.types.is_float_dtype(series):
        return "REAL"
    if pd.api.types.is_bool_dtype(series):
        return "INTEGER"
    # Try datetime
    try:
        s = series.dropna()
        if len(s) > 0:
            pd.to_datetime(s, errors="raise")
            return "TEXT"  # SQLite has no native datetime; store as ISO text
    except (ValueError, TypeError):
        pass
    return "TEXT"


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    cur = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    return cur.fetchone() is not None


def get_or_create_table(
    conn: sqlite3.Connection,
    table_name: str,
    df: pd.DataFrame,
) -> str:
    """Create table if not exists; return 'created' or 'existed'."""
    if table_exists(conn, table_name):
        logger.info("  Table %s already exists, skipping DDL", table_name)
        return "existed"

    col_defs: List[str] = []
    for col in df.columns:
        sql_type = infer_sqlite_type(df[col])
        safe_col = f'"{col}"'
        col_defs.append(f"{safe_col} {sql_type}")

    ddl = f'CREATE TABLE "{table_name}" (\n  ' + ",\n  ".join(col_defs) + "\n)"
    logger.info("  DDL:\n%s", ddl)
    conn.execute(ddl)
    conn.commit()
    logger.info("  Created table %s (%d columns)", table_name, len(df.columns))
    return "created"


def create_indexes(conn: sqlite3.Connection, table_name: str, df: pd.DataFrame):
    """Auto-create indexes on likely lookup columns."""
    index_candidates: List[str] = []
    for col in df.columns:
        lower = col.lower()
        if any(
            kw in lower
            for kw in (
                "id",
                "name",
                "title",
                "date",
                "time",
                "code",
                "province",
                "city",
                "district",
                "status",
                "type",
                "source",
            )
        ):
            index_candidates.append(col)

    for col in index_candidates:
        idx_name = f"idx_{table_name}_{col}"
        try:
            conn.execute(
                f'CREATE INDEX IF NOT EXISTS "{idx_name}" ON "{table_name}" ("{col}")'
            )
        except sqlite3.OperationalError as e:
            logger.warning("  Skip index on %s: %s", col, e)

    conn.commit()
    if index_candidates:
        logger.info(
            "  Created %d indexes: %s", len(index_candidates), index_candidates
        )


def import_csv(filepath: Path, conn: sqlite3.Connection) -> int:
    """Import a single CSV into SQLite. Returns row count."""
    fname = filepath.stem
    table_name = sanitize_table_name(fname)
    enc = detect_encoding(filepath)

    logger.info("─" * 60)
    logger.info("Importing %s → table '%s' (encoding=%s)", filepath.name, table_name, enc)

    df = pd.read_csv(filepath, encoding=enc, dtype=str, keep_default_na=False)
    df.columns = standardize_columns(list(df.columns))

    logger.info("  Columns: %s", list(df.columns))
    logger.info("  Rows in CSV: %d", len(df))

    get_or_create_table(conn, table_name, df)

    # Use INSERT OR REPLACE for idempotency
    placeholders = ", ".join(["?"] * len(df.columns))
    cols_quoted = ", ".join(f'"{c}"' for c in df.columns)
    insert_sql = f'INSERT OR REPLACE INTO "{table_name}" ({cols_quoted}) VALUES ({placeholders})'

    rows = [tuple(row) for row in df.itertuples(index=False)]
    conn.executemany(insert_sql, rows)
    conn.commit()

    create_indexes(conn, table_name, df)

    count = conn.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
    logger.info("  → Imported %d rows into '%s'", count, table_name)
    return count


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    logger.info("Database path: %s", DB_PATH)
    csv_files = sorted(
        [f for f in DATA_DIR.iterdir() if f.suffix.lower() == ".csv"]
    )

    if not csv_files:
        logger.warning("No CSV files found in %s", DATA_DIR)
        return

    logger.info("Found %d CSV file(s)", len(csv_files))

    # Remove existing DB to start fresh
    if DB_PATH.exists():
        DB_PATH.unlink()
        logger.info("Removed existing database")

    conn = sqlite3.connect(str(DB_PATH))

    totals: dict[str, int] = {}
    try:
        for fp in csv_files:
            n = import_csv(fp, conn)
            totals[fp.name] = n

        # ── Summary ────────────────────────────────────────────────
        logger.info("=" * 60)
        logger.info("Import summary:")
        grand_total = 0
        for fname, count in totals.items():
            logger.info("  %-40s %8d rows", fname, count)
            grand_total += count
        logger.info("  %-40s %8d rows (total)", "", grand_total)

        # Verify: list all tables
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        logger.info("Tables in database: %s", [t[0] for t in tables])

    finally:
        conn.close()

    logger.info("Done – database saved to %s", DB_PATH)


if __name__ == "__main__":
    main()
