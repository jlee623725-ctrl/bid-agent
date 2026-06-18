"""BidAgent: LLM agent with tool-calling loop, compatible with DeepSeek API."""

import logging
import os
import time
from typing import Any, Callable, Dict, Generator, List, Optional

from openai import OpenAI

logger = logging.getLogger(__name__)

MAX_ROUNDS = 10
MAX_RETRIES = 2
RETRY_BASE_DELAY = 1.0

ToolSchema = List[Dict[str, Any]]
ToolRegistry = Dict[str, Callable[..., str]]


class BidAgent:
    """LLM agent with OpenAI-compatible function calling, tuned for DeepSeek."""

    def __init__(
        self,
        system_prompt: str,
        tools: ToolSchema,
        tool_handlers: ToolRegistry,
        model: str = "deepseek-chat",
    ) -> None:
        if not system_prompt:
            raise ValueError("system_prompt must be non-empty")
        if not isinstance(tools, list):
            raise TypeError("tools must be a list of function-calling schemas")

        self.system_prompt = system_prompt
        self.tools = tools
        self.tool_handlers = tool_handlers
        self.model = model

        base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY environment variable is not set")

        self.client = OpenAI(api_key=api_key, base_url=base_url)
        logger.info(
            "BidAgent initialized: model=%s base_url=%s tools=%d handlers=%d",
            model,
            base_url,
            len(tools),
            len(tool_handlers),
        )

    # ── Public API ────────────────────────────────────────────────────────

    def run(self, user_input: str) -> str:
        """Execute the tool-calling loop and return the final assistant message."""
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_input},
        ]

        for round_num in range(1, MAX_ROUNDS + 1):
            t0 = time.perf_counter()
            logger.info("Round %d/%d — %d messages in context", round_num, MAX_ROUNDS, len(messages))

            response = self._call_api(messages, self.tools)

            choice = response.choices[0]
            finish_reason = choice.finish_reason
            elapsed = time.perf_counter() - t0
            logger.info("Round %d — finish_reason=%s elapsed=%.2fs", round_num, finish_reason, elapsed)

            if finish_reason == "stop":
                content = choice.message.content or ""
                logger.info("Agent finished: %d chars returned", len(content))
                return content

            if finish_reason == "tool_calls":
                assistant_msg = choice.message.model_dump(exclude_none=True)
                messages.append(assistant_msg)

                for tc in choice.message.tool_calls:
                    tool_name = tc.function.name
                    tool_args = tc.function.arguments
                    tool_call_id = tc.id
                    logger.info("  Calling tool: %s(%s)", tool_name, tool_args)

                    result = self._execute_tool(tool_name, tool_args)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": result,
                    })
                continue

            # Unexpected finish_reason (e.g., "length", "content_filter")
            logger.warning("Unexpected finish_reason=%s, returning raw content", finish_reason)
            return choice.message.content or ""

        logger.warning("Max rounds (%d) exceeded", MAX_ROUNDS)
        return "处理超时"

    def run_stream(self, user_input: str) -> Generator[str, None, None]:
        """Streaming variant — yields content delta tokens as they arrive.

        Note: When the model requests tool calls, the loop executes them
        internally and yields the final text response as a stream.
        """
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_input},
        ]

        for round_num in range(1, MAX_ROUNDS + 1):
            t0 = time.perf_counter()
            logger.info("Stream round %d/%d", round_num, MAX_ROUNDS)

            response = self._call_api(messages, self.tools)

            choice = response.choices[0]
            finish_reason = choice.finish_reason
            elapsed = time.perf_counter() - t0
            logger.info("Stream round %d — finish_reason=%s elapsed=%.2fs", round_num, finish_reason, elapsed)

            if finish_reason == "stop":
                content = choice.message.content or ""
                yield content
                return

            if finish_reason == "tool_calls":
                assistant_msg = choice.message.model_dump(exclude_none=True)
                messages.append(assistant_msg)

                for tc in choice.message.tool_calls:
                    tool_name = tc.function.name
                    tool_args = tc.function.arguments
                    tool_call_id = tc.id
                    logger.info("  Calling tool: %s(%s)", tool_name, tool_args)

                    result = self._execute_tool(tool_name, tool_args)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": result,
                    })
                continue

            logger.warning("Unexpected finish_reason=%s", finish_reason)
            yield choice.message.content or ""
            return

        logger.warning("Max rounds (%d) exceeded in stream mode", MAX_ROUNDS)
        yield "处理超时"

    # ── Internal helpers ──────────────────────────────────────────────────

    def _call_api(
        self,
        messages: List[Dict[str, Any]],
        tools: ToolSchema,
    ) -> Any:
        """Call the chat completions endpoint with retry logic."""
        last_exc: Optional[Exception] = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                return self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=tools,
                    stream=False,
                )
            except Exception as exc:
                last_exc = exc
                logger.error(
                    "API call failed (attempt %d/%d): %s",
                    attempt + 1,
                    MAX_RETRIES + 1,
                    exc,
                )
                if attempt < MAX_RETRIES:
                    delay = RETRY_BASE_DELAY * (2 ** attempt)
                    time.sleep(delay)
        raise RuntimeError(f"API call failed after {MAX_RETRIES + 1} attempts") from last_exc

    def _execute_tool(self, name: str, arguments: str) -> str:
        """Execute a registered tool and return its string output.

        Errors are caught and returned as error text so the model can
        self-correct rather than crashing the loop.
        """
        handler = self.tool_handlers.get(name)
        if handler is None:
            msg = f"Unknown tool: {name}"
            logger.error(msg)
            return msg

        import json

        try:
            args = json.loads(arguments) if arguments else {}
        except json.JSONDecodeError:
            args = {}

        try:
            result = handler(**args) if isinstance(args, dict) else handler(args)
            return str(result)
        except Exception as exc:
            msg = f"Tool execution error: {exc}"
            logger.error("%s.%s → %s", name, arguments, msg)
            return msg
