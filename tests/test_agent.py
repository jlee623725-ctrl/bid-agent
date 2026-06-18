"""Tests for BidAgent core — mocked API calls."""

import os
from unittest.mock import MagicMock, patch

import pytest

from agent.core import BidAgent


@pytest.fixture(autouse=True)
def set_api_key():
    os.environ["DEEPSEEK_API_KEY"] = "test-key"
    os.environ["DEEPSEEK_BASE_URL"] = "https://test.api"


def _make_mock_response(content=None, tool_calls=None, finish_reason="stop"):
    """Build a mock chat completion response object."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls or []

    choice = MagicMock()
    choice.finish_reason = finish_reason
    choice.message = msg

    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ── Tests ─────────────────────────────────────────────────────────────────


class TestAgentNoTools:
    def test_agent_returns_direct_text(self):
        agent = BidAgent(
            system_prompt="You are helpful.",
            tools=[],
            tool_handlers={},
        )

        with patch.object(agent.client.chat.completions, "create") as mock_create:
            mock_create.return_value = _make_mock_response(
                content="Hello! 你好！",
                finish_reason="stop",
            )

            result = agent.run("Hi")
            assert result == "Hello! 你好！"
            mock_create.assert_called_once()

    def test_agent_includes_system_prompt(self):
        agent = BidAgent(
            system_prompt="你是一个招标分析师。",
            tools=[],
            tool_handlers={},
        )

        with patch.object(agent.client.chat.completions, "create") as mock_create:
            mock_create.return_value = _make_mock_response(
                content="OK",
                finish_reason="stop",
            )

            agent.run("查询")
            call_args = mock_create.call_args.kwargs
            messages = call_args["messages"]
            assert messages[0]["role"] == "system"
            assert messages[0]["content"] == "你是一个招标分析师。"
            assert messages[1]["role"] == "user"
            assert messages[1]["content"] == "查询"


class TestAgentWithTool:
    def test_agent_executes_tool_and_returns_result(self):
        tools_schema = [
            {
                "type": "function",
                "function": {
                    "name": "echo",
                    "description": "Echo back",
                    "parameters": {
                        "type": "object",
                        "properties": {"text": {"type": "string"}},
                        "required": ["text"],
                    },
                },
            }
        ]

        def echo_handler(text: str) -> str:
            return f"ECHO: {text}"

        agent = BidAgent(
            system_prompt="You are helpful.",
            tools=tools_schema,
            tool_handlers={"echo": echo_handler},
        )

        with patch.object(agent.client.chat.completions, "create") as mock_create:
            # First call: model requests a tool call
            tc = MagicMock()
            tc.id = "call_001"
            tc.function.name = "echo"
            tc.function.arguments = '{"text": "hello"}'

            msg1 = MagicMock()
            msg1.content = None
            msg1.tool_calls = [tc]
            msg1.model_dump.return_value = {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call_001",
                        "type": "function",
                        "function": {"name": "echo", "arguments": '{"text": "hello"}'},
                    }
                ],
            }

            resp1 = MagicMock()
            resp1.choices = [MagicMock(finish_reason="tool_calls", message=msg1)]

            # Second call: model stops with final answer
            resp2 = _make_mock_response(
                content="工具返回了 ECHO: hello",
                finish_reason="stop",
            )

            mock_create.side_effect = [resp1, resp2]

            result = agent.run("echo hello please")
            assert "ECHO: hello" in result
            assert mock_create.call_count == 2

    def test_agent_handles_tool_execution_error_as_content(self):
        tools_schema = [
            {
                "type": "function",
                "function": {
                    "name": "broken",
                    "description": "Always fails",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

        def broken_handler() -> str:
            raise ValueError("模拟的工具错误")

        agent = BidAgent(
            system_prompt="You are helpful.",
            tools=tools_schema,
            tool_handlers={"broken": broken_handler},
        )

        with patch.object(agent.client.chat.completions, "create") as mock_create:
            tc = MagicMock()
            tc.id = "call_err"
            tc.function.name = "broken"
            tc.function.arguments = "{}"

            msg1 = MagicMock()
            msg1.content = None
            msg1.tool_calls = [tc]
            msg1.model_dump.return_value = {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call_err",
                        "type": "function",
                        "function": {"name": "broken", "arguments": "{}"},
                    }
                ],
            }

            resp1 = MagicMock()
            resp1.choices = [
                MagicMock(finish_reason="tool_calls", message=msg1)
            ]

            resp2 = _make_mock_response(
                content="工具调用失败了，让我换种方式回答...",
                finish_reason="stop",
            )

            mock_create.side_effect = [resp1, resp2]

            result = agent.run("test")
            assert mock_create.call_count == 2
            # Agent should recover and return final message
            assert len(result) > 0

    def test_agent_unknown_tool_returns_error_message(self):
        tools_schema = [
            {
                "type": "function",
                "function": {
                    "name": "known_tool",
                    "description": "A known tool",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

        agent = BidAgent(
            system_prompt="You are helpful.",
            tools=tools_schema,
            tool_handlers={"known_tool": lambda: "OK"},
        )

        with patch.object(agent.client.chat.completions, "create") as mock_create:
            # Model tries to call a tool not in the handler map
            tc = MagicMock()
            tc.id = "call_unk"
            tc.function.name = "unknown_tool"
            tc.function.arguments = "{}"

            msg1 = MagicMock()
            msg1.content = None
            msg1.tool_calls = [tc]
            msg1.model_dump.return_value = {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call_unk",
                        "type": "function",
                        "function": {"name": "unknown_tool", "arguments": "{}"},
                    }
                ],
            }

            resp1 = MagicMock()
            resp1.choices = [
                MagicMock(finish_reason="tool_calls", message=msg1)
            ]

            resp2 = _make_mock_response(
                content="无法使用那个工具...",
                finish_reason="stop",
            )

            mock_create.side_effect = [resp1, resp2]

            result = agent.run("test")
            # Should have continued despite unknown tool
            assert mock_create.call_count == 2
            assert result == "无法使用那个工具..."

    def test_agent_max_turns_exceeded_returns_timeout(self):
        agent = BidAgent(
            system_prompt="You are helpful.",
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "loop",
                        "description": "Loop",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
            tool_handlers={"loop": lambda: "OK"},
        )

        with patch.object(agent.client.chat.completions, "create") as mock_create:
            tc = MagicMock()
            tc.id = "call_loop"
            tc.function.name = "loop"
            tc.function.arguments = "{}"

            msg = MagicMock()
            msg.content = None
            msg.tool_calls = [tc]
            msg.model_dump.return_value = {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call_loop",
                        "type": "function",
                        "function": {"name": "loop", "arguments": "{}"},
                    }
                ],
            }

            resp = MagicMock()
            resp.choices = [
                MagicMock(finish_reason="tool_calls", message=msg)
            ]

            # Always returns tool_calls — so loop never ends
            mock_create.side_effect = [resp] * 20

            result = agent.run("test")
            assert mock_create.call_count == 10  # MAX_ROUNDS
            assert "超时" in result


class TestAgentApiRetry:
    def test_agent_retries_on_api_failure(self):
        agent = BidAgent(
            system_prompt="You are helpful.",
            tools=[],
            tool_handlers={},
        )

        with patch.object(agent.client.chat.completions, "create") as mock_create:
            # First two calls fail, third succeeds
            mock_create.side_effect = [
                Exception("API connection error"),
                Exception("API timeout"),
                _make_mock_response(content="终于成功了", finish_reason="stop"),
            ]

            result = agent.run("test")
            assert result == "终于成功了"
            assert mock_create.call_count == 3

    def test_agent_raises_after_max_retries(self):
        agent = BidAgent(
            system_prompt="You are helpful.",
            tools=[],
            tool_handlers={},
        )

        with patch.object(agent.client.chat.completions, "create") as mock_create:
            mock_create.side_effect = Exception("一直失败")

            with pytest.raises(RuntimeError, match="API call failed after"):
                agent.run("test")

            assert mock_create.call_count == 3  # 1 initial + 2 retries
