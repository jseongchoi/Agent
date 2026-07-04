from __future__ import annotations

import argparse
import json
from pathlib import Path

from semicon_agent.core.agent import SemiconductorAgent
from semicon_agent.core.artifacts import ArtifactStore
from semicon_agent.core.policy import ExecutionPolicy
from semicon_agent.core.session import SQLiteRunStore
from semicon_agent.llm.mock import MockLLM


DEFAULT_DATA_PATH = Path("examples/sample_wafer.csv")


def run_self_check(
    data_path: str | Path = DEFAULT_DATA_PATH,
    session_db: str | Path = ".semicon_agent/self_check.sqlite",
    artifact_root: str | Path = ".semicon_agent/artifacts",
) -> dict[str, object]:
    resolved_data = Path(data_path).expanduser().resolve()
    store = SQLiteRunStore(session_db)
    artifacts = ArtifactStore(artifact_root)
    policy = ExecutionPolicy(allowed_roots=(resolved_data.parent,))
    agent = SemiconductorAgent(llm=MockLLM(), policy=policy, run_store=store)

    run = agent.run("create an overall semiconductor data report", data_path=str(resolved_data), max_steps=3, stream=True)
    report_artifact = artifacts.save_text(f"self_checks/{run.run_id}.md", run.final_answer)
    tool_errors = [result.error for result in run.tool_results if result.error]
    ok = (
        resolved_data.exists()
        and not tool_errors
        and "Semiconductor Data Report" in run.final_answer
        and bool(store.get_events(run.run_id))
    )
    return {
        "ok": ok,
        "run_id": run.run_id,
        "data_path": str(resolved_data),
        "tool_count": len(run.tool_results),
        "step_count": run.step_count,
        "stop_reason": run.stop_reason,
        "report_artifact": report_artifact,
        "errors": tool_errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a serverless Semicon Agent self-check.")
    parser.add_argument("--data", default=str(DEFAULT_DATA_PATH))
    parser.add_argument("--session-db", default=".semicon_agent/self_check.sqlite")
    parser.add_argument("--artifact-root", default=".semicon_agent/artifacts")
    args = parser.parse_args()

    payload = run_self_check(data_path=args.data, session_db=args.session_db, artifact_root=args.artifact_root)
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    if not payload["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
