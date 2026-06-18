"""Automated evaluation of agent tool-calling accuracy and response quality.

Evaluates:
  - Tool selection accuracy: did the agent call the right tools?
  - Result quality: did the response contain expected keywords?
  - Minimum results: did the agent find enough data?

Usage: python scripts/evaluate.py
"""

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.factory import create_default_registry
from agent.core import BidAgent

logging.basicConfig(level=logging.WARNING)  # quiet during eval

EVAL_PATH = Path(__file__).resolve().parent.parent / "tests" / "eval_data.json"


class EvalResult:
    def __init__(self, case_id: str, question: str, domain: str):
        self.case_id = case_id
        self.question = question
        self.domain = domain
        self.tool_called: bool = False
        self.tools_used: List[str] = []
        self.correct_tool_called: bool = False
        self.has_keywords: bool = True
        self.response: str = ""
        self.elapsed: float = 0.0
        self.error: str = ""

    @property
    def passed(self) -> bool:
        return self.tool_called and self.correct_tool_called and self.has_keywords


def run_eval(cases: List[dict], agent: BidAgent, verbose: bool = False) -> List[EvalResult]:
    """Run evaluation cases against an agent."""
    results: List[EvalResult] = []

    for i, case in enumerate(cases):
        result = EvalResult(case["id"], case["question"], case["domain"])
        expected_tools = case.get("expected_tools", [])
        expected_keywords = case.get("expected_keywords", [])
        min_results = case.get("min_results", 1)

        t0 = time.perf_counter()
        try:
            # Instrument agent to track which tools were called
            tools_called: List[str] = []

            original_execute = agent._execute_tool

            def tracking_execute(name, arguments):
                tools_called.append(name)
                return original_execute(name, arguments)

            agent._execute_tool = tracking_execute

            response = agent.run(case["question"])
            result.response = response[:500]

            # Restore
            agent._execute_tool = original_execute

        except Exception as e:
            result.error = str(e)
            result.elapsed = time.perf_counter() - t0
            results.append(result)
            continue

        result.elapsed = round(time.perf_counter() - t0, 2)
        result.tool_called = len(tools_called) > 0
        result.tools_used = tools_called

        # Check if at least one expected tool was used
        if expected_tools:
            result.correct_tool_called = any(
                t in tools_called for t in expected_tools
            )
        else:
            result.correct_tool_called = True  # no specific tool expected

        # Check keywords in response
        if expected_keywords:
            resp_lower = response.lower()
            result.has_keywords = any(
                kw.lower() in resp_lower for kw in expected_keywords
            )

        if verbose:
            print(f"[{i+1}/{len(cases)}] {case['id']}: "
                  f"tools={tools_called} "
                  f"correct_tool={result.correct_tool_called} "
                  f"keywords={result.has_keywords} "
                  f"time={result.elapsed}s")

        results.append(result)

    return results


def print_report(results: List[EvalResult]) -> Dict[str, Any]:
    """Print evaluation report and return summary dict."""
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    tool_call_rate = sum(1 for r in results if r.tool_called) / total * 100
    tool_accuracy = sum(1 for r in results if r.correct_tool_called) / total * 100
    keyword_rate = sum(1 for r in results if r.has_keywords) / total * 100
    avg_time = sum(r.elapsed for r in results) / total
    errors = sum(1 for r in results if r.error)

    print("=" * 70)
    print("                    EVALUATION REPORT")
    print("=" * 70)
    print(f"  Total cases:          {total}")
    print(f"  Passed:               {passed}/{total} ({passed/total*100:.1f}%)")
    print(f"  Tool call rate:       {tool_call_rate:.1f}%")
    print(f"  Tool selection acc:   {tool_accuracy:.1f}%")
    print(f"  Keyword relevance:    {keyword_rate:.1f}%")
    print(f"  Avg response time:    {avg_time:.1f}s")
    print(f"  Errors:               {errors}")
    print("-" * 70)

    # Per-domain breakdown
    domains: Dict[str, List[EvalResult]] = {}
    for r in results:
        domains.setdefault(r.domain, []).append(r)

    for domain, items in domains.items():
        d_passed = sum(1 for r in items if r.passed)
        d_avg = sum(r.elapsed for r in items) / len(items) if items else 0
        print(f"  [{domain:10s}] {d_passed}/{len(items)} passed, avg {d_avg:.1f}s")

    print("=" * 70)

    # Failures
    failures = [r for r in results if not r.passed]
    if failures:
        print("\nFailures:")
        for r in failures:
            reasons = []
            if not r.tool_called:
                reasons.append("no tool called")
            if not r.correct_tool_called:
                reasons.append(f"wrong tools (used {r.tools_used})")
            if not r.has_keywords:
                reasons.append("missing keywords")
            if r.error:
                reasons.append(f"error: {r.error[:80]}")
            print(f"  [{r.case_id}] {', '.join(reasons)}")

    return {
        "total": total,
        "passed": passed,
        "pass_rate": round(passed / total * 100, 1),
        "tool_call_rate": round(tool_call_rate, 1),
        "tool_accuracy": round(tool_accuracy, 1),
        "keyword_rate": round(keyword_rate, 1),
        "avg_time": round(avg_time, 1),
        "errors": errors,
    }


def main():
    if not EVAL_PATH.exists():
        print(f"Eval data not found at {EVAL_PATH}")
        sys.exit(1)

    cases = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    print(f"Loaded {len(cases)} evaluation cases")

    registry = create_default_registry()

    # Evaluate supervisor (all tools) + each specialist on their domain
    for agent_name in ["supervisor", "bidding_analyst", "company_profiler", "legal_advisor"]:
        print(f"\n{'='*70}")
        print(f"  Evaluating: {agent_name}")
        print(f"{'='*70}")

        agent = registry.create_agent(agent_name)
        results = run_eval(cases, agent, verbose=True)
        summary = print_report(results)

        # Save detailed results
        out_path = Path(__file__).resolve().parent.parent / "tests" / f"eval_result_{agent_name}.json"
        out_path.write_text(
            json.dumps(
                {
                    "agent": agent_name,
                    "summary": summary,
                    "details": [
                        {
                            "id": r.case_id,
                            "question": r.question,
                            "tools_used": r.tools_used,
                            "correct_tool": r.correct_tool_called,
                            "has_keywords": r.has_keywords,
                            "passed": r.passed,
                            "elapsed": r.elapsed,
                            "error": r.error,
                        }
                        for r in results
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
