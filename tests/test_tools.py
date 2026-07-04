from pathlib import Path

from semicon_agent.tools.semiconductor import (
    anomaly_scan,
    correlation_scan,
    dataset_profile,
    spc_summary,
    yield_summary,
)


DATA_PATH = Path(__file__).parents[1] / "examples" / "sample_wafer.csv"


def test_dataset_profile_detects_measurement_columns() -> None:
    profile = dataset_profile(str(DATA_PATH))

    assert profile["row_count"] == 16
    assert "param_vth" in profile["measurement_columns"]
    assert profile["role_guess"]["wafer"] == "wafer_id"


def test_yield_summary_overall_and_by_wafer() -> None:
    summary = yield_summary(str(DATA_PATH))

    assert summary["total_count"] == 16
    assert summary["pass_count"] == 12
    assert summary["yield_pct"] == 75.0
    assert summary["by_wafer"]


def test_yield_summary_accepts_hard_bin_alias(tmp_path: Path) -> None:
    data = tmp_path / "bin.csv"
    data.write_text("wafer_id,hard_bin,param\n1,1,0.1\n1,2,0.2\n2,1,0.3\n", encoding="utf-8")

    summary = yield_summary(str(data))

    assert summary["pass_count"] == 2
    assert summary["yield_pct"] == 66.66666666666666
    assert summary["pass_source"] == "hard_bin == 1"


def test_yield_summary_accepts_string_status_alias(tmp_path: Path) -> None:
    data = tmp_path / "status.csv"
    data.write_text("wafer_id,status,param\n1,pass,0.1\n1,fail,0.2\n2,OK,0.3\n", encoding="utf-8")

    summary = yield_summary(str(data))

    assert summary["pass_count"] == 2
    assert summary["yield_pct"] == 66.66666666666666
    assert summary["pass_source"] == "status"


def test_spc_summary_supports_cpk_when_specs_are_given() -> None:
    summary = spc_summary(
        str(DATA_PATH),
        target_columns=["param_vth"],
        spec_limits={"param_vth": {"lsl": 0.45, "usl": 0.56}},
    )

    item = summary["columns"][0]
    assert item["column"] == "param_vth"
    assert item["cpk"] is not None


def test_anomaly_scan_finds_extreme_iddq_values() -> None:
    scan = anomaly_scan(str(DATA_PATH), z_threshold=2.0)

    iddq = next(item for item in scan["columns"] if item["column"] == "param_iddq")
    assert iddq["anomaly_count"] >= 1


def test_correlation_scan_returns_pass_correlations() -> None:
    scan = correlation_scan(str(DATA_PATH))

    assert scan["pass_correlations"]
    assert scan["pairwise_correlations"]
