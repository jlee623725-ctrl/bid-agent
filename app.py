"""Streamlit UI for the bidding agent platform."""

from dotenv import load_dotenv

load_dotenv()

import streamlit as st

from agent.factory import create_default_registry

# ── Page config ───────────────────────────────────────────────────────────

st.set_page_config(page_title="招投标智能体平台", page_icon="📋", layout="wide")

# ── Registry ──────────────────────────────────────────────────────────────

AGENT_OPTIONS = {
    "🤖 智能助理": "supervisor",
    "📊 标讯分析": "bidding_analyst",
    "🏢 企业画像": "company_profiler",
    "⚖️ 法规咨询": "legal_advisor",
}

MODEL_NAME = "deepseek-chat"


@st.cache_resource
def get_registry():
    return create_default_registry()


# ── Session state init ────────────────────────────────────────────────────

if "histories" not in st.session_state:
    st.session_state["histories"] = {
        "supervisor": [],
        "bidding_analyst": [],
        "company_profiler": [],
        "legal_advisor": [],
    }

if "current_agent" not in st.session_state:
    st.session_state["current_agent"] = "supervisor"


def current_history() -> list:
    return st.session_state["histories"][st.session_state["current_agent"]]


# ── Sidebar ───────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("⚙️ 配置")

    label = st.selectbox(
        "选择 Agent",
        options=list(AGENT_OPTIONS.keys()),
        index=0,
        key="agent_label",
    )
    agent_key = AGENT_OPTIONS[label]
    switch_and_clear = st.checkbox("切换Agent时清空对话历史", value=False)

    if agent_key != st.session_state["current_agent"]:
        if switch_and_clear:
            st.session_state["histories"][agent_key] = []
        st.session_state["current_agent"] = agent_key

    st.divider()
    st.caption(f"模型：{MODEL_NAME}")

# ── Title ─────────────────────────────────────────────────────────────────

st.title("📋 招投标智能体平台")
st.caption(f"当前 Agent：{label}")

# ── Chat messages ─────────────────────────────────────────────────────────

for msg in current_history():
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ── Chat input ────────────────────────────────────────────────────────────

user_input = st.chat_input("请输入您的问题...")

if user_input:
    history = current_history()
    history.append({"role": "user", "content": user_input})

    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("分析中..."):
            try:
                registry = get_registry()
                agent = registry.create_agent(agent_key, model=MODEL_NAME)
                response = agent.run(user_input)
            except Exception as e:
                response = f"❌ 调用失败：{e}"

        st.markdown(response)

    history.append({"role": "assistant", "content": response})
