from __future__ import annotations

import argparse
import json

from semicon_agent.config import AgentSettings, validate_max_steps
from semicon_agent.core.agent import AgentRun, SemiconductorAgent
from semicon_agent.core.approval import AutoApprovalProvider, ConsoleApprovalProvider
from semicon_agent.core.policy import ExecutionPolicy
from semicon_agent.core.session import SQLiteRunStore
from semicon_agent.core.trace import redact
from semicon_agent.llm.mock import MockLLM
from semicon_agent.llm.open_model import OpenModelLLM


def main() -> None:
    settings = AgentSettings.from_env()
    parser = argparse.ArgumentParser(description="Semiconductor data analysis agent.")
    parser.add_argument("request", nargs="?", help="Natural language analysis request.")
    parser.add_argument("--data", help="Path to CSV/TSV/XLSX semiconductor data.")
    parser.add_argument("--llm", choices=["mock", "open-model"], default="mock")
    parser.add_argument("--base-url", default=settings.open_model_base_url)
    parser.add_argument("--model", default=settings.open_model_name)
    parser.add_argument("--api-key", default=settings.open_model_api_key)
    parser.add_argument(
        "--allow-remote-llm",
        action="store_true",
        default=settings.allow_remote_llm,
        help="Allow non-local HTTPS open-model endpoints.",
    )
    parser.add_argument("--allow-root", action="append", default=[], help="Additional allowed data root. Can be used multiple times.")
    parser.add_argument(
        "--approve-risk",
        action="append",
        choices=["safe", "read", "write", "external", "destructive"],
        default=[],
        help="Approve a tool risk level for this run.",
    )
    parser.add_argument("--yes", action="store_true", help="Approve all tool risk levels for this run.")
    parser.add_argument("--interactive-approval", action="store_true", help="Prompt before running tools that require approval.")
    parser.add_argument("--max-steps", type=int, default=settings.max_steps, help="Maximum plan/act loop steps.")
    parser.add_argument("--stream", action="store_true", help="Use streaming-ready synthesis path.")
    parser.add_argument("--session-db", default=str(settings.session_db), help="SQLite run/session database path.")
    parser.add_argument("--list-runs", action="store_true", help="List recent persisted runs and exit.")
    parser.add_argument("--show-trace", help="Print persisted trace events for a run id and exit.")
    parser.add_argument("--json", action="store_true", help="Print redacted run payload as JSON.")
    parser.add_argument("--unsafe-json", action="store_true", help="Print raw run payload as JSON.")
    args = parser.parse_args()

    run_store = SQLiteRunStore(args.session_db)
    if args.list_runs:
        print(json.dumps(run_store.list_runs(), indent=2, ensure_ascii=False, default=str))
        return
    if args.show_trace:
        print(json.dumps(run_store.get_events(args.show_trace), indent=2, ensure_ascii=False, default=str))
        return
    if not args.request:
        parser.error("request is required unless --list-runs or --show-trace is used.")
    try:
        validate_max_steps(args.max_steps)
    except ValueError as exc:
        parser.error(str(exc))

    if args.llm == "open-model":
        llm = OpenModelLLM(
            base_url=args.base_url,
            model=args.model,
            api_key=args.api_key,
            allow_remote=args.allow_remote_llm,
        )
    else:
        llm = MockLLM()

    approved = {"safe", "read", "write", "external", "destructive"} if args.yes else {"safe", "read", *args.approve_risk}
    allowed_roots = settings.resolved_allowed_roots(extra_roots=tuple(args.allow_root))
    policy = ExecutionPolicy(approved_risks=frozenset(approved), allowed_roots=allowed_roots)
    approval_provider = AutoApprovalProvider() if args.yes else None
    if args.interactive_approval:
        approval_provider = ConsoleApprovalProvider()
    agent = SemiconductorAgent(llm=llm, policy=policy, run_store=run_store)
    run = agent.run(
        args.request,
        data_path=args.data,
        approval_provider=approval_provider,
        max_steps=args.max_steps,
        stream=args.stream,
    )

    if args.json or args.unsafe_json:
        print(json.dumps(_run_payload(run, redact_payload=not args.unsafe_json), indent=2, ensure_ascii=False, default=str))
    else:
        print(run.final_answer)
        print(f"\nrun_id: {run.run_id}")


def _run_payload(run: AgentRun, redact_payload: bool = True) -> dict[str, object]:
    payload = {
        "run_id": run.run_id,
        "request": run.request,
        "plan": run.plan.model_dump(),
        "plans": [plan.model_dump() for plan in run.plans],
        "tool_results": [result.model_dump() for result in run.tool_results],
        "final_answer": run.final_answer,
        "events": [event.to_dict() for event in run.events],
        "step_count": run.step_count,
        "stop_reason": run.stop_reason,
    }
    return redact(payload) if redact_payload else payload


if __name__ == "__main__":
    main()
