from __future__ import annotations

from semicon_agent.models import AgentPlan, ToolCall, ToolResult
from semicon_agent.tools.base import ToolSpec


class MockLLM:
    """Deterministic stand-in for an LLM during local development."""

    def plan(
        self,
        user_request: str,
        tools: list[ToolSpec],
        context: dict[str, object],
    ) -> AgentPlan:
        text = user_request.lower()
        data_path = context.get("data_path")
        if not data_path:
            return AgentPlan(
                reasoning="No data path was provided.",
                final_answer="Provide a data file with --data before running analysis.",
            )

        calls: list[ToolCall] = []

        wants_report = self._contains(text, ["report", "overall", "summary", "full", "all", "report", "rpt", "종합", "전체", "리포트", "보고서"])
        wants_yield = self._contains(text, ["yield", "bin", "pass", "fail", "수율", "불량", "양품"])
        wants_spc = self._contains(text, ["spc", "cpk", "cp", "control", "spec", "관리도", "공정능력", "관리"])
        wants_anomaly = self._contains(text, ["anomaly", "outlier", "abnormal", "이상", "특이", "아웃라이어"])
        wants_corr = self._contains(text, ["correlation", "corr", "relationship", "상관", "연관"])
        wants_profile = self._contains(text, ["profile", "columns", "schema", "데이터", "컬럼", "구조"])

        path_arg = {"path": str(data_path)}
        if wants_report:
            calls.append(ToolCall(name="make_semiconductor_report", arguments=path_arg))
        else:
            if wants_profile or not any([wants_yield, wants_spc, wants_anomaly, wants_corr]):
                calls.append(ToolCall(name="dataset_profile", arguments=path_arg))
            if wants_yield:
                calls.append(ToolCall(name="yield_summary", arguments=path_arg))
            if wants_spc:
                calls.append(ToolCall(name="spc_summary", arguments=path_arg))
            if wants_anomaly:
                calls.append(ToolCall(name="anomaly_scan", arguments=path_arg))
            if wants_corr:
                calls.append(ToolCall(name="correlation_scan", arguments=path_arg))

        return AgentPlan(
            reasoning="Mock planning selected semiconductor analysis tools by keyword.",
            tool_calls=calls,
        )

    def synthesize(
        self,
        user_request: str,
        tool_results: list[ToolResult],
        context: dict[str, object],
    ) -> str:
        if not tool_results:
            return "No tools were executed."

        lines = ["Mock LLM synthesis", ""]
        for result in tool_results:
            lines.append(f"## {result.name}")
            if result.error:
                lines.append(f"ERROR: {result.error}")
                lines.append("")
                continue
            lines.extend(self._summarize_output(result.output))
            lines.append("")
        return "\n".join(lines).strip()

    @staticmethod
    def _contains(text: str, keywords: list[str]) -> bool:
        return any(keyword in text for keyword in keywords)

    def _summarize_output(self, output: object) -> list[str]:
        if isinstance(output, str):
            return output.splitlines()
        if not isinstance(output, dict):
            return [repr(output)]

        kind = output.get("kind")
        if kind == "dataset_profile":
            return [
                f"Rows: {output['row_count']}, columns: {output['column_count']}",
                f"Numeric columns: {', '.join(output['numeric_columns']) or 'none'}",
                f"Missing cells: {output['missing_cells']}",
            ]
        if kind == "yield_summary":
            return [
                f"Total dies: {output['total_count']}",
                f"Passed dies: {output['pass_count']}",
                f"Yield: {output['yield_pct']:.2f}%",
                f"Detected pass source: {output['pass_source']}",
            ]
        if kind == "spc_summary":
            lines = []
            for item in output["columns"][:5]:
                cpk = item.get("cpk")
                cpk_text = "n/a" if cpk is None else f"{cpk:.3f}"
                lines.append(
                    f"{item['column']}: mean={item['mean']:.4g}, std={item['std']:.4g}, "
                    f"OOC={item['out_of_control_count']}, Cpk={cpk_text}"
                )
            return lines or ["No numeric measurement columns detected."]
        if kind == "anomaly_scan":
            return [
                f"Scanned columns: {len(output['columns'])}",
                f"Anomaly rows found: {output['total_anomaly_count']}",
            ]
        if kind == "correlation_scan":
            lines = []
            if output.get("pass_correlations"):
                best = output["pass_correlations"][0]
                lines.append(f"Top pass correlation: {best['column']} = {best['correlation']:.3f}")
            if output.get("pairwise_correlations"):
                best_pair = output["pairwise_correlations"][0]
                lines.append(
                    f"Top pairwise correlation: {best_pair['column_a']} vs "
                    f"{best_pair['column_b']} = {best_pair['correlation']:.3f}"
                )
            return lines or ["No usable correlations detected."]
        if kind == "markdown_report":
            return [output["markdown"]]
        return [str(output)]
