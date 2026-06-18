"""Agent factory with pre-registered analyst agents."""

from typing import Any, Callable, Dict, List

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

ToolSchema = List[Dict[str, Any]]
ToolMap = Dict[str, Callable[..., str]]


class AgentRegistry:
    """Registry of named agent configurations."""

    def __init__(self) -> None:
        self._agents: Dict[str, Dict[str, Any]] = {}

    def register(
        self,
        name: str,
        system_prompt: str,
        tools: ToolSchema,
        tool_map: ToolMap,
    ) -> None:
        self._agents[name] = {
            "system_prompt": system_prompt,
            "tools": tools,
            "tool_map": tool_map,
        }

    def create_agent(self, name: str, model: str = "deepseek-chat") -> BidAgent:
        config = self._agents[name]
        return BidAgent(
            system_prompt=config["system_prompt"],
            tools=config["tools"],
            tool_handlers=config["tool_map"],
            model=model,
        )

    def list_agents(self) -> List[str]:
        return list(self._agents.keys())


# ── Pre-built system prompts ──────────────────────────────────────────────

BIDDING_PROMPT = "你是招投标数据分析师，擅长从公告和交易记录中提取洞察。回答时要引用具体数据和金额。用中文回复。"

COMPANY_PROMPT = "你是企业信息分析师，帮用户查找和评估投标企业。回答要列出企业关键信息（注册资本、经营范围、所在地）。用中文回复。"

LEGAL_PROMPT = "你是招投标法规专家，回答要准确引用法律条文原文，注明出处（法律法规名称、第几条）。用中文回复。"


# ── Default registry ──────────────────────────────────────────────────────

def create_default_registry() -> AgentRegistry:
    reg = AgentRegistry()

    # Supervisor (all-domain orchestrator)
    all_schemas = bidding_schema + company_schema + legal_schema
    all_handlers = {
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

    reg.register(
        name="supervisor",
        system_prompt=SUPERVISOR_PROMPT,
        tools=all_schemas,
        tool_map=all_handlers,
    )

    reg.register(
        name="bidding_analyst",
        system_prompt=BIDDING_PROMPT,
        tools=bidding_schema,
        tool_map={
            "search_notices": search_notices,
            "query_trends": query_trends,
            "get_notice_detail": get_notice_detail,
        },
    )

    reg.register(
        name="company_profiler",
        system_prompt=COMPANY_PROMPT,
        tools=company_schema,
        tool_map={
            "search_companies": search_companies,
            "get_company_profile": get_company_profile,
            "find_competitors": find_competitors,
        },
    )

    reg.register(
        name="legal_advisor",
        system_prompt=LEGAL_PROMPT,
        tools=legal_schema,
        tool_map={
            "semantic_search_laws": semantic_search_laws,
            "search_laws": search_laws,
            "get_article": get_article,
        },
    )

    return reg
