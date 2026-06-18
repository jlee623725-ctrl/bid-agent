"""Supervisor Agent: multi-domain orchestrator with access to all tools.

Routes user queries across bidding, company, and legal domains.
Enables cross-domain reasoning like "analyze winners in Hefei construction".
"""

import logging
from typing import Any, Dict, List, Optional

from agent.core import BidAgent
from agent.tools_bidding import (
    get_notice_detail,
    query_trends,
    search_notices,
    tools_schema as bidding_schema,
)
from agent.tools_company import (
    find_competitors,
    get_company_profile,
    search_companies,
    tools_schema as company_schema,
)
from agent.tools_legal import (
    get_article,
    search_laws,
    semantic_search_laws,
    tools_schema as legal_schema,
)

logger = logging.getLogger(__name__)

SUPERVISOR_PROMPT = """你是招投标智能助理，拥有跨领域分析能力。你可同时使用以下工具：

【标讯分析工具】
- search_notices: 搜索招标公告
- query_trends: 统计行业中标趋势
- get_notice_detail: 查看公告详情

【企业分析工具】
- search_companies: 筛选企业（城市/行业/资本）
- get_company_profile: 企业全景画像（信息+中标记录+同行）
- find_competitors: 查找竞争对手

【法规政策工具】
- semantic_search_laws: 语义搜索法律法规和政策（推荐优先使用）
- search_laws: 关键词搜索法律法规
- get_article: 精确查询法条原文

工作流程：
1. 理解用户意图，判断涉及哪些领域
2. 按需调用工具，可能跨多个领域
3. 整合多领域信息，给出综合分析结论
4. 引用具体数据（金额、企业名、法条出处）
5. 用中文回复，结构清晰

示例场景：
- "合肥建筑行业有哪些中标企业" → search_companies + search_notices
- "某公司的竞争对手最近中了哪些标" → find_competitors + search_notices
- "中小企业投标有什么优惠政策" → semantic_search_laws + query_trends"""


def create_supervisor_agent(model: str = "deepseek-chat") -> BidAgent:
    """Build a supervisor agent with access to ALL tools."""
    all_schemas = bidding_schema + company_schema + legal_schema

    all_handlers: Dict[str, Any] = {
        "search_notices": search_notices,
        "query_trends": query_trends,
        "get_notice_detail": get_notice_detail,
        "search_companies": search_companies,
        "get_company_profile": get_company_profile,
        "find_competitors": find_competitors,
        "semantic_search_laws": semantic_search_laws,
        "search_laws": search_laws,
        "get_article": get_article,
    }

    logger.info(
        "Supervisor created: %d tools across 3 domains (bidding+company+legal)",
        len(all_schemas),
    )
    return BidAgent(
        system_prompt=SUPERVISOR_PROMPT,
        tools=all_schemas,
        tool_handlers=all_handlers,
        model=model,
    )
