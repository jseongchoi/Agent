# Semicon Agent Beginner Guide

이 문서는 `semicon-agent`를 처음 보는 사람이 프로젝트의 목적, 실행 방법, 내부 구조,
확장 방법을 순서대로 이해할 수 있도록 만든 입문 가이드다.

기존 `AGENT_GUIDE.md`가 전체 아키텍처와 장기 확장 방향을 다루는 문서라면, 이 문서는
"처음 받은 사람이 바로 설치하고, 실행하고, 코드를 어디서 봐야 하는지 이해하는 것"을
목표로 한다.

## 1. 이 프로젝트를 한 문장으로 설명하면

`semicon-agent`는 반도체 데이터 분석 업무에 사용할 수 있는 Python 기반 Agent
프레임워크 prototype이다.

여기서 Agent란 다음 일을 하는 프로그램이다.

1. 사용자의 자연어 요청을 받는다.
2. LLM 또는 mock LLM이 어떤 분석 tool을 쓸지 계획한다.
3. Python 함수로 구현된 분석 tool을 실행한다.
4. 실행 결과를 모아 최종 답변을 만든다.
5. 실행 과정과 결과를 trace/session/artifact로 저장한다.

현재 분석 함수는 production 수준의 정교한 반도체 통계 엔진이 아니다. 이 프로젝트의
핵심은 분석 정확도보다 "LLM이 tool을 고르고, runtime이 안전하게 실행하고, 결과를
기록하는 agent framework 구조"를 검증하는 것이다.

## 2. 왜 이런 구조가 필요한가

일반적인 챗봇은 사용자의 질문에 텍스트로 답한다. 하지만 반도체 데이터 분석 업무에서는
텍스트 답변만으로 부족하다.

현실적인 업무 흐름은 보통 다음과 같다.

1. CSV/Excel 같은 측정 데이터를 읽는다.
2. 수율, SPC, 이상치, 상관관계 같은 분석을 실행한다.
3. lot, wafer, bin, pass/fail 같은 반도체 업무 column을 해석한다.
4. 결과를 사람이 읽을 수 있는 report로 정리한다.
5. 분석 과정과 결과를 다시 확인할 수 있게 저장한다.

LLM은 자연어 이해와 계획에는 강하지만, 숫자 계산을 신뢰할 수 있게 직접 수행하는
도구는 아니다. 따라서 이 프로젝트는 LLM과 Python 분석 함수를 분리한다.

- LLM 계층: 어떤 tool을 호출할지 결정한다.
- Python tool 계층: 실제 계산을 수행한다.
- Agent runtime: LLM의 요청을 검증하고, tool을 실행하고, trace를 남긴다.

이 분리가 중요하다. LLM이 실수하더라도 tool argument validation, path policy,
approval policy 같은 runtime 안전장치가 중간에서 막아줄 수 있기 때문이다.

## 3. 전체 구조를 먼저 이해하기

가장 단순한 실행 흐름은 다음과 같다.

```text
사용자 요청
  -> SemiconductorAgent
  -> MockLLM 또는 OpenModelLLM
  -> AgentPlan 생성
  -> ToolRuntime
  -> semiconductor.py 분석 함수 실행
  -> ToolResult 수집
  -> 최종 답변 생성
  -> SQLite run store / artifact 저장
```

조금 더 풀어서 쓰면 다음과 같다.

```text
1. 사용자가 "analyze yield and SPC"라고 입력한다.
2. MockLLM이 요청 문장에서 "yield", "SPC"라는 키워드를 본다.
3. MockLLM은 yield_summary, spc_summary tool을 호출하라는 계획을 만든다.
4. SemiconductorAgent는 이 계획을 ToolRuntime에 넘긴다.
5. ToolRuntime은 argument schema와 path boundary를 검사한다.
6. semiconductor.py의 yield_summary, spc_summary 함수가 CSV를 읽고 계산한다.
7. MockLLM이 tool 결과를 사람이 읽을 수 있는 문장으로 합성한다.
8. 실행 trace와 최종 답변이 SQLite DB에 저장된다.
```

이 프로젝트에서 중요한 파일은 다음과 같다.

| 파일 | 역할 |
| --- | --- |
| `semicon_agent/core/agent.py` | Agent 실행 루프의 중심 |
| `semicon_agent/llm/mock.py` | 테스트용 deterministic LLM 대체 구현 |
| `semicon_agent/llm/open_model.py` | OpenAI-compatible open-model API 연결부 |
| `semicon_agent/tools/semiconductor.py` | demo 반도체 분석 함수들 |
| `semicon_agent/tools/runtime.py` | tool validation, path policy, approval 적용 |
| `semicon_agent/core/policy.py` | 허용 path, risk level 같은 실행 정책 |
| `semicon_agent/core/session.py` | SQLite run/session 저장소 |
| `semicon_agent/core/artifacts.py` | upload/report/self-check artifact 저장소 |
| `semicon_agent/server/api.py` | FastAPI server와 Web UI |
| `semicon_agent/cli.py` | CLI entrypoint |
| `semicon_agent/self_check.py` | 서버 없이 end-to-end 검증 |
| `tests/` | 회귀 테스트 |

## 4. 설치 전 준비물

필요한 기본 환경은 다음과 같다.

- Python 3.10 이상
- PowerShell 또는 일반 terminal
- Git
- 인터넷 연결. 처음 dependency 설치 시 필요하다.

현재 개발 환경에서는 Python 3.13에서도 테스트가 통과했다.

## 5. 설치

프로젝트 루트에서 다음 명령을 실행한다.

```powershell
python -m pip install -e ".[dev]"
```

이 명령의 의미는 다음과 같다.

- `-e`: editable install. 코드를 수정하면 재설치 없이 바로 반영된다.
- `.[dev]`: 기본 dependency와 개발/test/web dependency를 함께 설치한다.

단, `pyproject.toml`의 dependency나 console script가 바뀐 경우에는 editable install이라도
다시 설치해야 한다.

설치 후 정상 동작을 확인하려면 다음을 실행한다.

```powershell
python -m semicon_agent.self_check --data examples/sample_wafer.csv
```

정상이라면 대략 다음 형태의 JSON이 나온다.

```json
{
  "ok": true,
  "run_id": "...",
  "tool_count": 1,
  "step_count": 2,
  "stop_reason": "final_answer",
  "report_artifact": "self_checks/....md",
  "errors": []
}
```

`ok`가 `true`이면 최소 실행 경로가 정상이다.

## 6. 가장 먼저 실행해볼 명령

수율과 SPC demo 분석을 실행한다.

```powershell
python -m semicon_agent "analyze yield and SPC" --data examples/sample_wafer.csv
```

예상되는 출력은 다음과 비슷하다.

```text
Mock LLM synthesis

## yield_summary
Total dies: 16
Passed dies: 12
Yield: 75.00%
Detected pass source: is_pass

## spc_summary
param_vth: mean=0.5102, std=0.02422, OOC=0, Cpk=n/a
...

run_id: ...
```

이 출력에서 확인할 수 있는 것은 다음이다.

- sample data에는 총 16개 die가 있다.
- 12개가 pass로 계산된다.
- yield는 75%다.
- pass/fail 판정 column은 `is_pass`로 감지됐다.
- SPC demo tool은 numeric measurement column의 평균, 표준편차, OOC count를 계산했다.

종합 리포트를 생성하려면 다음을 실행한다.

```powershell
python -m semicon_agent "create an overall semiconductor data report" --data examples/sample_wafer.csv
```

## 7. sample data는 어떻게 생겼는가

샘플 파일은 `examples/sample_wafer.csv`다.

이 프로젝트의 demo tool은 다음과 같은 column 이름을 이해한다.

| 역할 | 대표 column |
| --- | --- |
| lot | `lot_id`, `lot`, `batch` |
| wafer | `wafer_id`, `wafer` |
| bin | `hard_bin`, `soft_bin`, `bin` |
| pass/fail | `is_pass`, `pass`, `result`, `status` |
| 측정값 | numeric column 중 ID/bin/pass/fail이 아닌 column |

지원하는 파일 형식은 다음이다.

- `.csv`
- `.tsv`
- `.txt`
- `.xlsx`
- `.xls`

pass/fail 판정 규칙은 다음 순서로 적용된다.

1. `is_pass`, `pass`, `result`, `status` column이 있으면 우선 사용한다.
2. boolean이면 `True`를 pass로 본다.
3. numeric이면 `0`이 아닌 값을 pass로 본다.
4. string이면 `pass`, `passed`, `ok`, `good`, `true`, `1`, `y`, `yes`를 pass로 본다.
5. pass/fail column이 없으면 `hard_bin == 1`, `soft_bin == 1`, `bin == 1`을 pass로 본다.

실제 업무에서는 이 규칙을 그대로 쓰기보다 회사/공정/제품별 schema에 맞게 조정해야 한다.

## 8. CLI 사용법

기본 구조는 다음과 같다.

```powershell
python -m semicon_agent "<요청문>" --data <데이터파일>
```

자주 쓰는 명령은 다음과 같다.

| 명령 | 목적 |
| --- | --- |
| `python -m semicon_agent "analyze yield" --data examples/sample_wafer.csv` | 수율 분석 |
| `python -m semicon_agent "analyze SPC" --data examples/sample_wafer.csv` | SPC demo 분석 |
| `python -m semicon_agent "find anomalies" --data examples/sample_wafer.csv` | 이상치 demo 분석 |
| `python -m semicon_agent "show correlations" --data examples/sample_wafer.csv` | 상관관계 demo 분석 |
| `python -m semicon_agent "create an overall report" --data examples/sample_wafer.csv` | 종합 report |
| `python -m semicon_agent --list-runs` | 저장된 run 목록 |
| `python -m semicon_agent --show-trace <run_id>` | 특정 run의 trace 확인 |

JSON payload로 전체 결과를 보고 싶으면 `--json`을 쓴다.

```powershell
python -m semicon_agent "create an overall report" --data examples/sample_wafer.csv --json
```

`--json`은 민감 정보와 경로를 redaction한다. 원시 payload를 반드시 봐야 하는 개발
상황에서는 `--unsafe-json`을 쓴다.

```powershell
python -m semicon_agent "create an overall report" --data examples/sample_wafer.csv --unsafe-json
```

`--unsafe-json`은 민감 정보가 출력될 수 있으므로 로그 공유 시 사용하면 안 된다.

## 9. Web UI와 API server 실행

로컬 Web UI를 실행하려면 다음을 사용한다.

```powershell
python -m semicon_agent.server --host 127.0.0.1 --port 8008 --allow-root examples
```

브라우저에서 다음 주소를 연다.

```text
http://127.0.0.1:8008
```

`--allow-root examples`는 API server가 `examples` 폴더 안의 데이터 파일을 읽을 수
있게 허용하는 옵션이다. 서버는 아무 파일이나 읽으면 안 되므로 allowed root boundary가
있다.

주요 endpoint는 다음과 같다.

| Endpoint | 설명 |
| --- | --- |
| `GET /health` | 최소 상태 확인 |
| `GET /api/status` | tool 수, run 수, artifact 수 확인 |
| `GET /` | 간단한 Web UI |
| `POST /api/artifacts` | 데이터 파일 업로드 |
| `GET /api/artifacts` | artifact 목록 |
| `GET /api/artifacts/{name}` | artifact 다운로드 |
| `POST /api/runs` | agent 실행 |
| `GET /api/runs` | 최근 run 목록 |
| `GET /api/runs/{run_id}` | run 상태와 최종 답변 조회 |
| `GET /api/runs/{run_id}/trace` | run trace 조회 |
| `GET /api/runs/{run_id}/otel` | 관측성용 span-like trace export |
| `POST /api/jobs` | background job으로 agent 실행 |
| `GET /api/jobs` | 최근 job 목록 |
| `GET /api/jobs/{job_id}` | job 상태 조회 |
| `DELETE /api/jobs/{job_id}` | queued job 취소 또는 running job 취소 요청 |
| `POST /api/jobs/{job_id}/retry` | failed/cancelled job 재시도 |

API server의 기본 보안 정책은 다음과 같다.

- 클라이언트가 LLM `base_url`, `api_key`, remote 허용값을 직접 바꾸는 것은 차단한다.
- 클라이언트가 risk approval을 직접 여는 것도 차단한다.
- `/api/status`는 기본적으로 로컬 절대 경로를 숨긴다.
- 상세 경로 상태는 `--debug-status`를 명시해야만 나온다.
- `SEMICON_AGENT_API_TOKEN` 또는 `--api-token`이 설정되면 `/api/*`는 bearer token을 요구한다.
- `SEMICON_AGENT_API_TOKENS`를 쓰면 `read`, `write`, `admin` 역할 토큰을 나눌 수 있다.
- API 오류는 `detail`과 함께 `error.code`, `error.category`, `error.retryable`을 반환한다.
- run/job 응답은 기본적으로 compact payload다. plan, tool result, event까지 보려면 request body에 `debug: true`를 넣는다.
- job status/result metadata와 재시작 복구용 request payload는 SQLite job DB에 저장된다.

이 정책은 이 프로젝트가 localhost prototype이어도 나중에 네트워크에 노출될 가능성을
고려한 기본 방어선이다.

긴 실행은 `/api/jobs`를 쓰는 것이 낫다. `/api/runs`는 요청 안에서 바로 실행하고
결과를 반환한다. `/api/jobs`는 `202 Accepted`와 `job_id`를 먼저 반환하고,
`GET /api/jobs/{job_id}`로 `queued`, `running`, `completed`, `failed`, `cancelled` 상태를 확인한다.
서버를 다시 띄워도 완료/실패 job metadata는 `SEMICON_AGENT_JOB_DB`에 남아 조회할 수 있다.
payload가 남은 `queued`/`running` job은 서버 시작 시 같은 `job_id`로 다시 실행 큐에 들어간다.
job 응답에는 현재 단계용 `progress`와 취소 요청 여부인 `cancel_requested`가 포함된다.
running job 취소는 Python thread를 강제로 죽이는 방식이 아니라 agent가 다음 안전 경계에서 멈추는 cooperative cancellation이다.

role token 예시는 다음과 같다.

```powershell
$env:SEMICON_AGENT_API_TOKENS="read:reader-token,write:writer-token,admin:admin-token"
```

`reader-token`은 조회만 가능하고, `writer-token`은 분석 실행과 업로드까지 가능하다.

## 10. MockLLM과 OpenModelLLM의 차이

현재 기본값은 `MockLLM`이다.

`MockLLM`은 실제 LLM이 아니다. 테스트를 위해 만든 deterministic 대체 구현이다.
사용자 요청에 들어 있는 keyword를 보고 tool을 고른다.

예를 들어 다음 요청은:

```text
analyze yield and SPC
```

대략 다음 tool plan으로 바뀐다.

```json
{
  "tool_calls": [
    {"name": "yield_summary", "arguments": {"path": "..."}},
    {"name": "spc_summary", "arguments": {"path": "..."}}
  ]
}
```

`OpenModelLLM`은 OpenAI-compatible `/chat/completions` API에 연결하는 adapter다.
나중에 Ollama, vLLM, LM Studio, OpenRouter 같은 open-model endpoint를 붙일 때 이
계층을 사용한다.

CLI에서 open-model을 쓰려면 다음처럼 실행한다.

```powershell
$env:OPEN_MODEL_API_KEY="..."
python -m semicon_agent "analyze yield" `
  --data examples/sample_wafer.csv `
  --llm open-model `
  --base-url http://localhost:8000/v1 `
  --model my-open-model
```

localhost가 아닌 endpoint는 HTTPS여야 하고, CLI에서 `--allow-remote-llm`을 명시해야
한다. 기본은 외부 endpoint 차단이다.

## 11. 내부 실행을 코드 기준으로 따라가기

이 절은 코드를 처음 읽는 사람이 어느 파일부터 보면 되는지 설명한다.

### 11-1. CLI에서 시작

사용자가 다음 명령을 실행한다고 가정한다.

```powershell
python -m semicon_agent "analyze yield" --data examples/sample_wafer.csv
```

시작점은 다음 파일이다.

```text
semicon_agent/__main__.py
```

여기서 `semicon_agent.cli.main()`을 호출한다.

### 11-2. CLI가 LLM과 policy를 만든다

다음 파일을 본다.

```text
semicon_agent/cli.py
```

여기서 하는 일은 다음이다.

1. argparse로 CLI option을 읽는다.
2. `--llm mock`이면 `MockLLM`을 만든다.
3. `--llm open-model`이면 `OpenModelLLM`을 만든다.
4. allowed root와 approved risk를 바탕으로 `ExecutionPolicy`를 만든다.
5. `SemiconductorAgent.run()`을 호출한다.

### 11-3. Agent가 plan-act loop를 실행한다

다음 파일이 핵심이다.

```text
semicon_agent/core/agent.py
```

`SemiconductorAgent.run()`은 다음 일을 한다.

1. run id와 trace recorder를 만든다.
2. data path를 context에 넣는다.
3. LLM에게 plan을 요청한다.
4. plan에 들어 있는 tool call을 순서대로 실행한다.
5. tool 결과를 모은다.
6. 필요하면 다시 planning한다.
7. 최종 synthesis를 요청한다.
8. run end event와 결과를 SQLite에 저장한다.

LLM planning 또는 synthesis에서 예외가 나면 `run.error` event를 남기고 run status를
`failed`로 저장한다.

### 11-4. ToolRuntime이 안전장치를 적용한다

다음 파일을 본다.

```text
semicon_agent/tools/runtime.py
```

ToolRuntime은 tool 실행 전에 다음을 검사한다.

1. tool 이름이 registry에 존재하는가
2. arguments가 schema에 맞는가
3. path argument가 allowed root 안에 있는가
4. tool risk level이 승인되어 있는가
5. approval이 필요한 tool이면 승인 provider가 허용했는가

이 과정을 통과해야 실제 Python 함수가 실행된다.

### 11-5. 실제 분석 함수는 semiconductor.py에 있다

다음 파일을 본다.

```text
semicon_agent/tools/semiconductor.py
```

현재 제공되는 demo tool은 다음이다.

| Tool | 설명 |
| --- | --- |
| `dataset_profile` | row/column, dtype, missing, role guess |
| `yield_summary` | 전체 및 wafer별 pass/fail yield |
| `spc_summary` | 평균, 표준편차, min/max, 3-sigma, rough Cpk |
| `anomaly_scan` | z-score 기반 이상치 demo |
| `correlation_scan` | numeric correlation demo |
| `make_semiconductor_report` | 여러 tool 결과를 markdown report로 결합 |

실제 업무에서 분석 정확도를 높이려면 대부분 이 파일을 확장하게 된다.

## 12. Tool을 새로 추가하는 방법

예를 들어 wafer map 요약 tool을 추가한다고 가정한다.

### 12-1. 분석 함수를 만든다

`semicon_agent/tools/semiconductor.py`에 함수를 추가한다.

```python
def wafer_map_summary(path: str) -> dict[str, object]:
    df = load_table(path)
    return {
        "kind": "wafer_map_summary",
        "row_count": len(df),
        "column_count": len(df.columns),
    }
```

### 12-2. ToolSpec으로 등록한다

같은 파일의 `build_semiconductor_tools()`에 ToolSpec을 추가한다.

```python
ToolSpec(
    name="wafer_map_summary",
    description="Demo tool: summarize wafer map table shape.",
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
        "additionalProperties": False,
    },
    handler=wafer_map_summary,
    risk_level="read",
    data_access=("table",),
)
```

중요한 점은 `parameters` schema다. LLM이 아무 argument나 넣어도 runtime이 schema로
막을 수 있어야 한다.

### 12-3. MockLLM keyword rule을 추가한다

테스트용 mock LLM이 이 tool을 고르게 하려면 `semicon_agent/llm/mock.py`를 수정한다.

예를 들어 사용자가 `wafer map`이라고 요청하면 `wafer_map_summary`를 호출하도록
keyword rule을 추가한다.

### 12-4. 테스트를 추가한다

`tests/test_tools.py`에 함수 단위 테스트를 추가한다.

```python
def test_wafer_map_summary() -> None:
    summary = wafer_map_summary(str(DATA_PATH))
    assert summary["row_count"] == 16
```

Agent가 실제로 tool을 선택하는지도 테스트하려면 `tests/test_agent.py` 또는
`tests/test_runtime_core.py`에 추가한다.

## 13. LLM provider를 새로 붙이는 방법

새 LLM provider는 `BaseLLM` protocol을 만족해야 한다.

필수 메서드는 다음 두 개다.

```python
def plan(user_request, tools, context) -> AgentPlan:
    ...

def synthesize(user_request, tool_results, context) -> str:
    ...
```

선택적으로 streaming-ready 경로를 제공할 수 있다.

```python
def stream_synthesize(user_request, tool_results, context):
    ...
```

provider를 추가할 때는 다음 원칙을 지킨다.

1. LLM에게 보내는 context에서 민감 정보와 전체 path를 redaction한다.
2. model output은 반드시 `AgentPlan` schema로 검증한다.
3. model이 이상한 JSON을 반환하면 tool을 실행하지 않는다.
4. remote endpoint는 기본 차단하고, 필요한 경우 명시적으로만 허용한다.
5. timeout, retry, rate limit을 provider 계층에 넣는다.

현재 `OpenModelLLM`은 OpenAI-compatible API의 최소 adapter다. production 수준으로
쓰려면 provider별 true streaming, retry, backoff, structured output 강제를 추가해야 한다.
remote LLM에 tool result를 보낼 때는 원본 전체가 아니라 요약 payload를 보내도록 되어 있다.

## 14. 실행 결과는 어디에 저장되는가

기본 저장 위치는 `.semicon_agent/` 아래다.

```text
.semicon_agent/
  runs.sqlite
  self_check.sqlite
  artifacts/
    reports/
    uploads/
    self_checks/
```

이 폴더는 `.gitignore`에 포함되어 있다. 즉 run history와 artifact는 GitHub에 올라가지
않는다.

저장되는 정보는 다음과 같다.

| 저장소 | 내용 |
| --- | --- |
| SQLite run store | run id, request, status, final answer, trace events |
| artifact store | uploaded dataset, generated report, self-check report |

최근 run을 보려면 다음을 실행한다.

```powershell
python -m semicon_agent --list-runs
```

특정 run의 trace를 보려면 다음을 실행한다.

```powershell
python -m semicon_agent --show-trace <run_id>
```

trace는 agent가 어떤 순서로 LLM plan, tool execution, synthesis를 수행했는지 확인하는
디버깅 자료다.

## 15. 테스트 구조

전체 테스트는 다음 명령으로 실행한다.

```powershell
python -m pytest -p no:cacheprovider
```

서버 없이 전체 agent smoke check와 eval도 실행할 수 있다.

```powershell
python -m semicon_agent.self_check --data examples/sample_wafer.csv
python -m semicon_agent.eval
```

현재 테스트가 확인하는 것은 다음이다.

| 테스트 파일 | 확인 내용 |
| --- | --- |
| `tests/test_tools.py` | 반도체 demo tool 계산 |
| `tests/test_agent.py` | MockLLM 기반 agent 실행 |
| `tests/test_runtime_core.py` | validation, policy, failure persistence |
| `tests/test_core_v2.py` | multi-step orchestration, approval, stream path |
| `tests/test_server_api.py` | FastAPI endpoint, upload, API guard |
| `tests/test_config_artifacts_self_check.py` | 설정, artifact, self-check |
| `tests/test_eval.py` | deterministic agent eval suite |

새 기능을 추가할 때는 최소한 다음 중 하나의 테스트를 추가해야 한다.

- 분석 함수만 바꿨다면 `tests/test_tools.py`
- agent loop를 바꿨다면 `tests/test_runtime_core.py`
- API를 바꿨다면 `tests/test_server_api.py`
- CLI나 설정을 바꿨다면 self-check 또는 config test

## 16. 자주 발생하는 문제와 해결

### 16-1. `ModuleNotFoundError: fastapi`

개발 dependency가 설치되지 않은 상태다.

```powershell
python -m pip install -e ".[dev]"
```

### 16-2. `Path is outside allowed roots`

Agent 또는 API server가 허용된 폴더 밖의 파일을 읽으려 했다.

CLI에서는 `--allow-root`를 추가한다.

```powershell
python -m semicon_agent "analyze yield" --data D:\data\lot.csv --allow-root D:\data
```

Server에서는 `--allow-root`를 추가한다.

```powershell
python -m semicon_agent.server --allow-root D:\data
```

### 16-3. Open-model remote endpoint가 거부된다

localhost가 아닌 endpoint는 기본 차단이다. remote endpoint를 쓰려면 HTTPS여야 하고,
명시적으로 허용해야 한다.

CLI 예시:

```powershell
python -m semicon_agent "analyze yield" `
  --data examples/sample_wafer.csv `
  --llm open-model `
  --base-url https://example.com/v1 `
  --model my-model `
  --allow-remote-llm
```

### 16-4. API에서 client LLM config가 거부된다

서버는 기본적으로 클라이언트가 LLM endpoint와 API key를 직접 넘기는 것을 차단한다.

개발 목적으로 허용하려면 서버를 다음처럼 실행한다.

```powershell
python -m semicon_agent.server --allow-client-llm-config
```

이 옵션은 서버를 외부에 노출하는 환경에서는 신중히 써야 한다.

### 16-5. Excel 파일이 느리다

현재 demo tool은 pandas/openpyxl로 파일 전체를 읽는다. row/column/cell/file-size limit,
parser timeout, upload content sniffing, chunked upload write는 들어갔다. `SEMICON_AGENT_PARSER_MODE=process`를
설정하면 table parser를 별도 process로 실행해 timeout 시 종료할 수 있다. 다만 production
수준에서는 CSV/parquet 변환과 형식별 parser profile을 추가하는 것이 좋다.

## 17. 현재 구현의 한계

이 프로젝트는 완성된 상용 분석 플랫폼이 아니다. 현재 보장하지 않는 것은 다음이다.

- 실제 반도체 공정 통계의 정확성
- 대용량 파일 streaming 처리 성능
- enterprise authentication/authorization
- enterprise audit/compliance
- true token streaming
- external durable job queue와 exactly-once 실행 보장
- resumable workflow
- long-term semantic memory
- configurable remote LLM outbound policy
- per-format parser sandbox policy

따라서 현재 코드는 "Agent framework prototype"으로 보고, 실제 업무 적용 전에는 보안,
성능, 인증, 분석 정확도, 운영 관측성을 추가로 hardening해야 한다.

## 18. 앞으로 개발할 때 우선순위

실제로 최신 Agent platform에 가까워지려면 다음 순서가 현실적이다.

1. External durable worker: 현재 in-process resumable job을 별도 worker/queue 구조로 바꾼다.
2. Run/job status endpoint 확장: timeout 정책과 더 상세한 progress event를 추가한다.
3. True streaming: SSE 또는 WebSocket으로 token/tool event를 실시간 전송한다.
4. Remote LLM policy: remote LLM에 보낼 payload를 tool별 summary와 정책으로 제한한다.
5. Upload hardening: per-format parser sandbox profile을 넣는다.
6. Auth boundary: API server에 사용자 ID, token rotation, enterprise identity를 둔다.
7. Workflow graph: long-running/resumable approval이 가능한 graph executor를 만든다.
8. Semiconductor tool pack: wafer map, bin pareto, lot trend, recipe comparison을 추가한다.

## 19. 처음 보는 사람이 읽을 순서

추천 순서는 다음이다.

1. `README.md`: 프로젝트가 무엇인지 빠르게 본다.
2. `docs/BEGINNER_GUIDE.md`: 설치, 실행, 내부 흐름을 따라간다.
3. `docs/AGENT_GUIDE.md`: agent 원리, Codex/Claude Code와의 관계, 장기 설계를 읽는다.
4. `docs/LATEST_AGENT_TODO.md`: 최신 에이전트 기준 TODO와 구현 내역을 확인한다.
5. `docs/IMPROVEMENT_AUDIT.md`: 검증된 항목과 남은 개선 backlog를 확인한다.
6. `tests/`: 실제로 무엇을 보장하는지 확인한다.
7. `semicon_agent/tools/semiconductor.py`: 반도체 분석 함수 확장 지점을 확인한다.
8. `semicon_agent/core/agent.py`: agent loop를 이해한다.
9. `semicon_agent/server/api.py`: API/UI 사용 흐름을 이해한다.

이 순서대로 보면 프로젝트를 처음 보는 사람도 "어떻게 실행하고, 어디를 고치고, 어떤
한계가 있는지"를 파악할 수 있다.
