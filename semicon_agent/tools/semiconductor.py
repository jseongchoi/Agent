from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from semicon_agent.tools.base import ToolSpec


ROLE_CANDIDATES = {
    "lot": ["lot_id", "lot", "batch"],
    "wafer": ["wafer_id", "wafer"],
    "bin": ["hard_bin", "soft_bin", "bin"],
    "pass": ["is_pass", "pass", "result", "status"],
}
NON_MEASUREMENT_HINTS = {
    "lot",
    "lot_id",
    "wafer",
    "wafer_id",
    "die",
    "die_x",
    "die_y",
    "x",
    "y",
    "bin",
    "hard_bin",
    "soft_bin",
    "pass",
    "is_pass",
}
MAX_TABLE_ROWS = 200_000
MAX_TABLE_COLUMNS = 500


def build_semiconductor_tools() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="dataset_profile",
            description="Demo tool: inspect table shape, columns, dtypes, and likely semiconductor roles.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
            handler=dataset_profile,
            risk_level="read",
            data_access=("table",),
        ),
        ToolSpec(
            name="yield_summary",
            description="Demo tool: calculate simple pass/fail yield overall and by wafer.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
            handler=yield_summary,
            risk_level="read",
            data_access=("table",),
        ),
        ToolSpec(
            name="spc_summary",
            description="Demo tool: return basic mean/std/min/max and optional rough Cpk.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "target_columns": {"type": "array", "items": {"type": "string"}},
                    "spec_limits": {"type": "object"},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
            handler=spc_summary,
            risk_level="read",
            data_access=("table",),
        ),
        ToolSpec(
            name="anomaly_scan",
            description="Demo tool: flag numeric values outside a z-score threshold.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "z_threshold": {"type": "number", "default": 3.0, "minimum": 0.1, "maximum": 10.0},
                    "max_examples": {"type": "integer", "default": 10, "minimum": 1, "maximum": 100},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
            handler=anomaly_scan,
            risk_level="read",
            data_access=("table",),
        ),
        ToolSpec(
            name="correlation_scan",
            description="Demo tool: rank simple numeric correlations.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "max_pairs": {"type": "integer", "default": 10, "minimum": 1, "maximum": 100},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
            handler=correlation_scan,
            risk_level="read",
            data_access=("table",),
        ),
        ToolSpec(
            name="make_semiconductor_report",
            description="Demo tool: combine the lightweight semiconductor tools into markdown.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
            handler=make_semiconductor_report,
            risk_level="read",
            data_access=("table",),
        ),
    ]


def dataset_profile(path: str) -> dict[str, Any]:
    df = load_table(path)
    role_guess = {role: _pick_column(df, candidates) for role, candidates in ROLE_CANDIDATES.items()}
    missing_by_column = {
        column: int(count)
        for column, count in df.isna().sum().items()
        if int(count) > 0
    }
    return _safe(
        {
            "kind": "dataset_profile",
            "path": str(Path(path)),
            "row_count": len(df),
            "column_count": len(df.columns),
            "columns": list(df.columns),
            "dtypes": {column: str(dtype) for column, dtype in df.dtypes.items()},
            "numeric_columns": list(df.select_dtypes(include=[np.number]).columns),
            "measurement_columns": _measurement_columns(df),
            "role_guess": role_guess,
            "missing_cells": int(df.isna().sum().sum()),
            "missing_by_column": missing_by_column,
        }
    )


def yield_summary(path: str) -> dict[str, Any]:
    df = load_table(path)
    pass_values, pass_source = _pass_values(df)
    work = df.copy()
    work["_pass"] = pass_values

    total = len(work)
    passed = int(work["_pass"].sum())
    wafer_column = _pick_column(work, ROLE_CANDIDATES["wafer"])
    lot_column = _pick_column(work, ROLE_CANDIDATES["lot"])

    by_lot = _yield_groups(work, [lot_column])
    by_wafer = _yield_groups(work, [lot_column, wafer_column])

    return _safe(
        {
            "kind": "yield_summary",
            "total_count": int(total),
            "pass_count": passed,
            "fail_count": int(total - passed),
            "yield_pct": _pct(passed, total),
            "pass_source": pass_source,
            "by_lot": by_lot,
            "by_wafer": by_wafer,
        }
    )


def spc_summary(
    path: str,
    target_columns: list[str] | None = None,
    spec_limits: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    df = load_table(path)
    spec_limits = spec_limits or {}
    columns = target_columns or _measurement_columns(df)
    rows = []

    for column in columns:
        if column not in df.columns:
            continue
        series = pd.to_numeric(df[column], errors="coerce").dropna()
        if series.empty:
            continue
        mean = float(series.mean())
        std = float(series.std(ddof=1)) if len(series) > 1 else 0.0
        limits = spec_limits.get(column, {})
        cpk = _rough_cpk(mean, std, limits.get("lsl"), limits.get("usl"))
        rows.append(
            {
                "column": column,
                "count": int(series.count()),
                "mean": mean,
                "std": std,
                "min": float(series.min()),
                "max": float(series.max()),
                "lcl_3sigma": mean - 3 * std,
                "ucl_3sigma": mean + 3 * std,
                "out_of_control_count": int(((series < mean - 3 * std) | (series > mean + 3 * std)).sum()),
                "cpk": cpk,
            }
        )

    return _safe({"kind": "spc_summary", "columns": rows})


def anomaly_scan(path: str, z_threshold: float = 3.0, max_examples: int = 10) -> dict[str, Any]:
    df = load_table(path)
    rows = []
    total = 0

    for column in _measurement_columns(df):
        series = pd.to_numeric(df[column], errors="coerce").dropna()
        if len(series) < 2:
            continue
        std = float(series.std(ddof=1))
        if std == 0:
            mask = pd.Series(False, index=series.index)
            z = pd.Series(0.0, index=series.index)
        else:
            z = (series - float(series.mean())) / std
            mask = z.abs() >= z_threshold
        examples = [
            {"row": int(index), "value": float(series.loc[index]), "z_score": float(z.loc[index])}
            for index in series[mask].index[:max_examples]
        ]
        count = int(mask.sum())
        total += count
        rows.append({"column": column, "anomaly_count": count, "examples": examples})

    rows.sort(key=lambda row: row["anomaly_count"], reverse=True)
    return _safe({"kind": "anomaly_scan", "z_threshold": z_threshold, "total_anomaly_count": total, "columns": rows})


def correlation_scan(path: str, max_pairs: int = 10) -> dict[str, Any]:
    df = load_table(path)
    measurement_columns = _measurement_columns(df)
    numeric = df[measurement_columns].apply(pd.to_numeric, errors="coerce") if measurement_columns else pd.DataFrame()

    pass_correlations = []
    try:
        pass_values, _ = _pass_values(df)
        for column in numeric.columns:
            corr = numeric[column].corr(pass_values.astype(float))
            if pd.notna(corr):
                pass_correlations.append({"column": column, "correlation": float(corr)})
    except ValueError:
        pass

    pairwise = []
    corr = numeric.corr()
    for index, column_a in enumerate(corr.columns):
        for column_b in corr.columns[index + 1 :]:
            value = corr.loc[column_a, column_b]
            if pd.notna(value):
                pairwise.append({"column_a": column_a, "column_b": column_b, "correlation": float(value)})

    pass_correlations.sort(key=lambda row: abs(row["correlation"]), reverse=True)
    pairwise.sort(key=lambda row: abs(row["correlation"]), reverse=True)
    return _safe(
        {
            "kind": "correlation_scan",
            "pass_correlations": pass_correlations[:max_pairs],
            "pairwise_correlations": pairwise[:max_pairs],
        }
    )


def make_semiconductor_report(path: str) -> dict[str, Any]:
    profile = dataset_profile(path)
    yield_data = yield_summary(path)
    spc = spc_summary(path)
    anomalies = anomaly_scan(path, z_threshold=2.0)
    correlations = correlation_scan(path)

    markdown = [
        "# Semiconductor Data Report",
        "",
        "## Dataset",
        f"- Rows: {profile['row_count']}",
        f"- Columns: {profile['column_count']}",
        f"- Measurement columns: {', '.join(profile['measurement_columns']) or 'none'}",
        "",
        "## Yield",
        f"- Yield: {yield_data['yield_pct']:.2f}%",
        f"- Pass/Fail: {yield_data['pass_count']} / {yield_data['fail_count']}",
        "",
        "## SPC Snapshot",
    ]
    for item in spc["columns"][:5]:
        markdown.append(f"- {item['column']}: mean={item['mean']:.4g}, std={item['std']:.4g}")
    markdown.extend(["", "## Anomaly Snapshot", f"- Total z-score flags: {anomalies['total_anomaly_count']}"])
    markdown.extend(["", "## Correlation Snapshot"])
    for item in correlations["pass_correlations"][:5]:
        markdown.append(f"- Pass vs {item['column']}: {item['correlation']:.3f}")

    return _safe(
        {
            "kind": "markdown_report",
            "markdown": "\n".join(markdown),
            "sections": {
                "profile": profile,
                "yield": yield_data,
                "spc": spc,
                "anomalies": anomalies,
                "correlations": correlations,
            },
        }
    )


def load_table(path: str, max_rows: int = MAX_TABLE_ROWS, max_columns: int = MAX_TABLE_COLUMNS) -> pd.DataFrame:
    table_path = Path(path).expanduser().resolve()
    if not table_path.exists():
        raise FileNotFoundError(f"Data file not found: {table_path}")
    if table_path.suffix.lower() == ".csv":
        return _enforce_table_limits(pd.read_csv(table_path, nrows=max_rows + 1), table_path, max_rows, max_columns)
    if table_path.suffix.lower() in {".tsv", ".txt"}:
        return _enforce_table_limits(pd.read_csv(table_path, sep="\t", nrows=max_rows + 1), table_path, max_rows, max_columns)
    if table_path.suffix.lower() in {".xlsx", ".xls"}:
        return _enforce_table_limits(pd.read_excel(table_path, nrows=max_rows + 1), table_path, max_rows, max_columns)
    raise ValueError(f"Unsupported data file type: {table_path.suffix}")


def _enforce_table_limits(df: pd.DataFrame, path: Path, max_rows: int, max_columns: int) -> pd.DataFrame:
    if len(df) > max_rows:
        raise ValueError(f"Table exceeds row limit of {max_rows}: {path}")
    if len(df.columns) > max_columns:
        raise ValueError(f"Table exceeds column limit of {max_columns}: {path}")
    return df


def _measurement_columns(df: pd.DataFrame) -> list[str]:
    columns = []
    for column in df.select_dtypes(include=[np.number]).columns:
        name = str(column).lower()
        if name not in NON_MEASUREMENT_HINTS and not name.endswith("_id"):
            columns.append(str(column))
    return columns


def _pass_values(df: pd.DataFrame) -> tuple[pd.Series, str]:
    column = _pick_column(df, ROLE_CANDIDATES["pass"])
    if column:
        series = df[column]
        if pd.api.types.is_bool_dtype(series):
            return series.fillna(False).astype(bool), column
        if pd.api.types.is_numeric_dtype(series):
            return series.fillna(0).astype(float).ne(0), column
        lowered = series.astype(str).str.lower().str.strip()
        return lowered.isin({"pass", "passed", "ok", "good", "true", "1", "y", "yes"}), column

    bin_column = _pick_column(df, ROLE_CANDIDATES["bin"])
    if bin_column:
        return pd.to_numeric(df[bin_column], errors="coerce").eq(1), f"{bin_column} == 1"

    raise ValueError("Could not detect pass/fail information.")


def _yield_groups(df: pd.DataFrame, columns: list[str | None]) -> list[dict[str, Any]]:
    group_columns = [column for column in columns if column]
    if not group_columns:
        return []
    grouped = df.groupby(group_columns, dropna=False)["_pass"].agg(total_count="size", pass_count="sum").reset_index()
    grouped["fail_count"] = grouped["total_count"] - grouped["pass_count"]
    grouped["yield_pct"] = grouped["pass_count"] / grouped["total_count"] * 100
    return _safe(grouped.sort_values("yield_pct").to_dict(orient="records"))


def _pick_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    by_lower = {str(column).lower(): str(column) for column in df.columns}
    for candidate in candidates:
        if candidate in by_lower:
            return by_lower[candidate]
    return None


def _rough_cpk(mean: float, std: float, lsl: float | None, usl: float | None) -> float | None:
    if std == 0 or lsl is None or usl is None:
        return None
    return min((float(usl) - mean) / (3 * std), (mean - float(lsl)) / (3 * std))


def _pct(part: int, total: int) -> float:
    return 0.0 if total == 0 else part / total * 100


def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_safe(item) for item in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    return value
