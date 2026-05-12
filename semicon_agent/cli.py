from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict

from semicon_agent.core.agent import SemiconductorAgent
from semicon_agent.llm.mock import MockLLM
from semicon_agent.llm.open_model import OpenModelLLM


def main() -> None:
    parser = argparse.ArgumentParser(description="Semiconductor data analysis agent.")
    parser.add_argument("request", help="Natural language analysis request.")
    parser.add_argument("--data", help="Path to CSV/TSV/XLSX semiconductor data.")
    parser.add_argument("--llm", choices=["mock", "open-model"], default="mock")
    parser.add_argument("--base-url", default=os.getenv("OPEN_MODEL_BASE_URL", "http://localhost:8000/v1"))
    parser.add_argument("--model", default=os.getenv("OPEN_MODEL_NAME", "open-model"))
    parser.add_argument("--api-key", default=os.getenv("OPEN_MODEL_API_KEY"))
    parser.add_argument("--json", action="store_true", help="Print full run payload as JSON.")
    args = parser.parse_args()

    if args.llm == "open-model":
        llm = OpenModelLLM(base_url=args.base_url, model=args.model, api_key=args.api_key)
    else:
        llm = MockLLM()

    agent = SemiconductorAgent(llm=llm)
    run = agent.run(args.request, data_path=args.data)

    if args.json:
        payload = asdict(run)
        payload["plan"] = run.plan.model_dump()
        payload["tool_results"] = [result.model_dump() for result in run.tool_results]
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    else:
        print(run.final_answer)


if __name__ == "__main__":
    main()
