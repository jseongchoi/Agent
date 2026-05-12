from pathlib import Path

from semicon_agent import MockLLM, SemiconductorAgent


DATA_PATH = Path(__file__).parents[1] / "examples" / "sample_wafer.csv"


def test_mock_agent_runs_selected_tools() -> None:
    agent = SemiconductorAgent(llm=MockLLM())

    run = agent.run("analyze yield and SPC", data_path=str(DATA_PATH))

    tool_names = [result.name for result in run.tool_results]
    assert tool_names == ["yield_summary", "spc_summary"]
    assert "Yield: 75.00%" in run.final_answer
    assert "param_vth" in run.final_answer


def test_mock_agent_creates_report() -> None:
    agent = SemiconductorAgent(llm=MockLLM())

    run = agent.run("create an overall report", data_path=str(DATA_PATH))

    assert [result.name for result in run.tool_results] == ["make_semiconductor_report"]
    assert "Semiconductor Data Report" in run.final_answer
