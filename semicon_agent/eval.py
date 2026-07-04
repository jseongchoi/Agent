from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from semicon_agent.core.artifacts import ArtifactStore
from semicon_agent.core.policy import ExecutionPolicy
from semicon_agent.core.session import SQLiteRunStore
from semicon_agent.llm.mock import MockLLM
from semicon_agent.core.agent import SemiconductorAgent


CheckFn = Callable[[str], bool]


@dataclass(frozen=True)
class EvalCase:
    name: str
    request: str
    checks: dict[str, CheckFn]


DEFAULT_EVAL_CASES = [
    EvalCase(
        name="yield",
        request="analyze yield",
        checks={"mentions_expected_yield": lambda answer: "Yield: 75.00%" in answer},
    ),
    EvalCase(
        name="spc",
        request="analyze SPC",
        checks={
            "mentions_spc_tool": lambda answer: "## spc_summary" in answer,
            "mentions_mean": lambda answer: "mean=" in answer,
        },
    ),
    EvalCase(
        name="report",
        request="create an overall semiconductor data report",
        checks={
            "creates_report": lambda answer: "# Semiconductor Data Report" in answer,
            "mentions_dataset": lambda answer: "## Dataset" in answer,
        },
    ),
]


def run_eval_suite(
    data_path: str | Path = "examples/sample_wafer.csv",
    session_db: str | Path = ".semicon_agent/eval.sqlite",
    artifact_root: str | Path = ".semicon_agent/artifacts",
) -> dict[str, object]:
    data_file = Path(data_path).expanduser().resolve()
    run_store = SQLiteRunStore(session_db)
    artifact_store = ArtifactStore(artifact_root)
    agent = SemiconductorAgent(
        llm=MockLLM(),
        policy=ExecutionPolicy(allowed_roots=(data_file.parent,)),
        run_store=run_store,
    )

    cases = []
    for case in DEFAULT_EVAL_CASES:
        started = time.time()
        run = agent.run(case.request, data_path=str(data_file), max_steps=3, stream=True)
        checks = {name: check(run.final_answer) for name, check in case.checks.items()}
        cases.append(
            {
                "name": case.name,
                "request": case.request,
                "ok": all(checks.values()) and not any(result.error for result in run.tool_results),
                "checks": checks,
                "run_id": run.run_id,
                "duration_ms": round((time.time() - started) * 1000, 2),
                "stop_reason": run.stop_reason,
                "tool_errors": [result.error for result in run.tool_results if result.error],
            }
        )

    passed = sum(1 for case in cases if case["ok"])
    payload: dict[str, object] = {
        "ok": passed == len(cases),
        "case_count": len(cases),
        "passed_count": passed,
        "failed_count": len(cases) - passed,
        "cases": cases,
    }
    payload["artifact"] = artifact_store.save_json(f"eval/{int(time.time())}.json", payload)
    return payload


def main() -> None:
    payload = run_eval_suite()
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    sys.exit(0 if payload["ok"] else 1)


if __name__ == "__main__":
    main()
