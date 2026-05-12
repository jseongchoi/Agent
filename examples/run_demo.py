from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from semicon_agent import MockLLM, SemiconductorAgent


if __name__ == "__main__":
    data_path = Path(__file__).with_name("sample_wafer.csv")
    agent = SemiconductorAgent(llm=MockLLM())
    run = agent.run("create an overall semiconductor data report", data_path=str(data_path))
    print(run.final_answer)
