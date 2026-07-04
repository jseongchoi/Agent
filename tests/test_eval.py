from __future__ import annotations

from pathlib import Path

from semicon_agent.eval import run_eval_suite


DATA_PATH = Path(__file__).parents[1] / "examples" / "sample_wafer.csv"


def test_eval_suite_runs_deterministic_cases(tmp_path: Path) -> None:
    payload = run_eval_suite(
        data_path=DATA_PATH,
        session_db=tmp_path / "eval.sqlite",
        artifact_root=tmp_path / "artifacts",
    )

    assert payload["ok"] is True
    assert payload["case_count"] == 3
    assert payload["passed_count"] == 3
    assert str(payload["artifact"]).startswith("eval/")
