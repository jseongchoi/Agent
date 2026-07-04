from __future__ import annotations

import argparse

import uvicorn

from semicon_agent.server.api import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Semicon Agent API server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8008)
    parser.add_argument("--session-db", default=".semicon_agent/runs.sqlite")
    parser.add_argument("--artifact-root", default=".semicon_agent/artifacts")
    args = parser.parse_args()
    uvicorn.run(
        create_app(session_db=args.session_db, artifact_root=args.artifact_root),
        host=args.host,
        port=args.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
