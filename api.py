"""FastAPI backend for the Bidding Agent Platform.

Exposes agents as REST endpoints with conversation management.

Usage: uvicorn api:app --reload --port 8000
"""

import uuid
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agent.factory import create_default_registry

app = FastAPI(
    title="招投标智能体平台 API",
    description="Bidding Agent Platform — multi-agent RAG system",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

registry = create_default_registry()

# In-memory conversation store (session_id → messages)
sessions: Dict[str, List[Dict[str, str]]] = {}


# ── Pydantic models ───────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    agent_name: str = Field(
        default="supervisor",
        description="Agent name: supervisor, bidding_analyst, company_profiler, legal_advisor",
    )
    message: str = Field(..., description="User message")
    session_id: Optional[str] = Field(default=None, description="Session ID for conversation continuity")
    model: str = Field(default="deepseek-chat", description="Model name")


class ChatResponse(BaseModel):
    session_id: str
    agent_name: str
    response: str
    model: str


class AgentInfo(BaseModel):
    name: str
    tools_count: int


class AgentListResponse(BaseModel):
    agents: List[AgentInfo]


# ── Endpoints ─────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"service": "招投标智能体平台 API", "version": "1.0.0", "docs": "/docs"}


@app.get("/agents", response_model=AgentListResponse)
def list_agents():
    """List all available agents with tool counts."""
    agents = []
    for name in registry.list_agents():
        config = registry._agents[name]
        agents.append(AgentInfo(name=name, tools_count=len(config["tools"])))
    return AgentListResponse(agents=agents)


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """Send a message to an agent. Session continuity by session_id."""
    if req.agent_name not in registry.list_agents():
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{req.agent_name}' not found. Available: {registry.list_agents()}",
        )

    session_id = req.session_id or str(uuid.uuid4())[:8]

    try:
        agent = registry.create_agent(req.agent_name, model=req.model)
        response_text = agent.run(req.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {e}")

    # Store in session history
    if session_id not in sessions:
        sessions[session_id] = []
    sessions[session_id].append({"role": "user", "content": req.message})
    sessions[session_id].append({"role": "assistant", "content": response_text})

    return ChatResponse(
        session_id=session_id,
        agent_name=req.agent_name,
        response=response_text,
        model=req.model,
    )


@app.get("/sessions/{session_id}")
def get_session(session_id: str):
    """Retrieve conversation history for a session."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session_id": session_id, "messages": sessions[session_id]}


@app.get("/health")
def health():
    return {"status": "ok"}
