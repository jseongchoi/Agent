from __future__ import annotations

import argparse

import uvicorn

from semicon_agent.config import AgentSettings
from semicon_agent.server.api import create_app


def main() -> None:
    settings = AgentSettings.from_env()
    parser = argparse.ArgumentParser(description="Run the Semicon Agent API server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8008)
    parser.add_argument("--session-db", default=str(settings.session_db))
    parser.add_argument("--artifact-root", default=str(settings.artifact_root))
    parser.add_argument("--allow-root", action="append", default=[], help="Additional allowed data root.")
    parser.add_argument("--default-llm", choices=["mock", "open-model"], default="mock")
    parser.add_argument("--allow-client-llm-config", action="store_true")
    parser.add_argument("--allow-client-risk-approval", action="store_true")
    parser.add_argument("--debug-status", action="store_true")
    parser.add_argument("--api-token", default=settings.api_token)
    parser.add_argument("--job-workers", type=int, default=2)
    args = parser.parse_args()
    uvicorn.run(
        create_app(
            session_db=args.session_db,
            artifact_root=args.artifact_root,
            allowed_roots=settings.resolved_allowed_roots(extra_roots=tuple(args.allow_root)),
            default_llm=args.default_llm,
            open_model_base_url=settings.open_model_base_url,
            open_model_name=settings.open_model_name,
            open_model_api_key=settings.open_model_api_key,
            allow_remote_llm=settings.allow_remote_llm,
            allow_client_llm_config=args.allow_client_llm_config,
            allow_client_risk_approval=args.allow_client_risk_approval,
            debug_status=args.debug_status,
            api_token=args.api_token,
            job_workers=args.job_workers,
        ),
        host=args.host,
        port=args.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
