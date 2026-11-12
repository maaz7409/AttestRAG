import json
import uuid

from fastapi.testclient import TestClient

from app.services.generation import NO_ANSWER
from app.services.pipeline import BLOCKED_MESSAGE, TOXIC_MESSAGE


def upload(client: TestClient, data: bytes, name: str = "handbook.pdf"):
    return client.post("/api/documents", files={"file": (name, data, "application/pdf")})


def stream_events(client: TestClient, payload: dict) -> list[dict]:
    events = []
    with client.stream("POST", "/api/chat/stream", json=payload) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        for line in response.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


def drain(client: TestClient) -> None:
    client.portal.call(client.app.state.services.pipeline.drain)


class ScriptedGenerator:
    """Generator double that always produces the same answer."""

    model_name = "scripted"

    def __init__(self, answer: str) -> None:
        self.answer = answer

    async def astream(self, question, chunks, history=()):
        for word in self.answer.split(" "):
            yield word + " "


def test_health_and_readiness(client: TestClient):
    assert client.get("/api/health").json() == {"status": "ok"}
    ready = client.get("/api/ready").json()
    assert ready["status"] == "ok"
    assert ready["checks"] == {"postgres": "ok", "qdrant": "ok"}
    assert ready["embedding_provider"] == "local"


def test_document_lifecycle(client: TestClient, handbook_pdf: bytes):
    response = upload(client, handbook_pdf)
    assert response.status_code == 201, response.text
    doc = response.json()
    assert doc["status"] == "ready" and doc["num_pages"] == 3 and doc["num_chunks"] >= 3

    assert upload(client, handbook_pdf, "copy.pdf").status_code == 409
    assert [d["id"] for d in client.get("/api/documents").json()] == [doc["id"]]
    assert client.get("/api/ready").json()["indexed_chunks"] == doc["num_chunks"]

    assert client.delete(f"/api/documents/{doc['id']}").status_code == 204
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 404
    assert client.get("/api/documents").json() == []
    assert client.get("/api/ready").json()["indexed_chunks"] == 0


def test_upload_validation(client: TestClient):
    bad_type = client.post("/api/documents", files={"file": ("notes.txt", b"hi", "text/plain")})
    assert bad_type.status_code == 415
    fake_pdf = client.post(
        "/api/documents", files={"file": ("x.pdf", b"not a pdf", "application/pdf")}
    )
    assert fake_pdf.status_code == 415


def test_streaming_chat_end_to_end(client: TestClient, handbook_pdf: bytes):
    upload(client, handbook_pdf)
    events = stream_events(
        client, {"question": "How many days of paid vacation do employees get?", "session_id": "s1"}
    )
    types = [e["type"] for e in events]
    assert types[0] == "start" and types[1] == "sources" and types[-1] == "done"
    assert types.index("evaluation") > max(i for i, t in enumerate(types) if t == "token")

    answer = "".join(e["content"] for e in events if e["type"] == "token")
    assert "25 days" in answer and "[" in answer

    sources = events[1]["sources"]
    assert sources and sources[0]["page_number"] == 1
    assert {"dense_score", "sparse_score", "fused_score", "filename"} <= sources[0].keys()

    evaluation = next(e for e in events if e["type"] == "evaluation")
    assert evaluation["passed"] is True and evaluation["faithfulness"] >= 0.6

    done = events[-1]
    assert done["status"] == "answered" and 1 in done["cited"]
    assert done["latency"]["total_ms"] >= done["latency"]["retrieval_ms"]

    # The query trail was written asynchronously.
    drain(client)
    trail = client.get("/api/queries").json()
    assert trail["total"] == 1
    detail = client.get(f"/api/queries/{done['query_id']}").json()
    assert detail["session_id"] == "s1"
    assert detail["evaluation"]["passed"] is True
    assert any(s["cited"] for s in detail["sources"])


def test_json_chat_endpoint_and_document_filter(client: TestClient, handbook_pdf, pdf_factory):
    upload(client, handbook_pdf)
    other = upload(client, pdf_factory(["The cafeteria serves vegan lunch every Friday."]))
    other_id = other.json()["id"]

    body = client.post(
        "/api/chat", json={"question": "vacation days", "document_ids": [other_id]}
    ).json()
    assert {s["document_id"] for s in body["sources"]} == {other_id}

    body = client.post("/api/chat", json={"question": "What does policy EXP-4471 require?"}).json()
    assert body["status"] == "answered"
    assert "EXP-4471" in body["answer"]
    assert body["sources"][0]["page_number"] == 2
    assert body["evaluation"]["judge_model"] == "heuristic-offline"


def test_no_documents_returns_refusal(client: TestClient):
    events = stream_events(client, {"question": "What is the vacation policy?"})
    assert "".join(e.get("content", "") for e in events if e["type"] == "token") == NO_ANSWER
    assert events[-1]["status"] == "no_context"


def test_hallucinated_answer_is_blocked(client: TestClient, handbook_pdf: bytes):
    upload(client, handbook_pdf)
    client.app.state.services.pipeline.generator = ScriptedGenerator(
        "The company was founded on Mars in 1802 by pirates."
    )
    events = stream_events(client, {"question": "How many vacation days?"})
    blocked = next(e for e in events if e["type"] == "blocked")
    assert blocked["reasons"] == ["faithfulness"] and blocked["message"] == BLOCKED_MESSAGE
    assert events[-1]["status"] == "blocked"

    drain(client)
    assert client.get("/api/queries?status=blocked").json()["total"] == 1


def test_toxic_answer_is_blocked(client: TestClient, handbook_pdf: bytes):
    upload(client, handbook_pdf)
    client.app.state.services.pipeline.generator = ScriptedGenerator(
        "Employees get 25 days of paid vacation, you stupid idiot [1]."
    )
    body = client.post("/api/chat", json={"question": "How many vacation days?"}).json()
    assert body["status"] == "blocked" and body["answer"] == TOXIC_MESSAGE
    assert "toxicity" in body["evaluation"]["failed_checks"]


def test_strict_mode_withholds_tokens_until_judged(client: TestClient, handbook_pdf: bytes):
    upload(client, handbook_pdf)
    pipeline = client.app.state.services.pipeline
    pipeline.guardrail_mode = "strict"

    events = stream_events(client, {"question": "How many days of paid vacation?"})
    types = [e["type"] for e in events]
    assert types.index("evaluation") < types.index("token")

    pipeline.generator = ScriptedGenerator("Pirates founded the company on Mars.")
    events = stream_events(client, {"question": "How many days of paid vacation?"})
    assert "token" not in [e["type"] for e in events]
    assert events[-1]["status"] == "blocked"


def test_judge_outage_fails_open(client: TestClient, handbook_pdf: bytes):
    upload(client, handbook_pdf)

    class BrokenJudge:
        model_name = "broken"

        async def grade(self, *args):
            raise TimeoutError("judge timed out")

    client.app.state.services.pipeline.evaluator.judge = BrokenJudge()
    events = stream_events(client, {"question": "How many days of paid vacation?"})
    assert "evaluation" not in [e["type"] for e in events]
    assert events[-1]["status"] == "answered"


def test_query_not_found(client: TestClient):
    assert client.get(f"/api/queries/{uuid.uuid4()}").status_code == 404


def test_analytics_overview(client: TestClient, handbook_pdf: bytes):
    upload(client, handbook_pdf)
    client.post("/api/chat", json={"question": "How many days of paid vacation?"})
    client.post("/api/chat", json={"question": "What does policy EXP-4471 require?"})
    client.app.state.services.pipeline.generator = ScriptedGenerator("Pirates on Mars.")
    client.post("/api/chat", json={"question": "Who founded the company?"})
    drain(client)

    overview = client.get("/api/analytics/overview?days=7").json()
    assert overview["totals"]["queries"] == 3
    assert overview["totals"]["blocked"] == 1
    assert overview["totals"]["documents"] == 1
    assert overview["quality"]["evaluated"] == 3
    assert 0 < overview["quality"]["pass_rate"] < 1
    assert overview["latency"]["p95_total_ms"] >= overview["latency"]["p50_total_ms"]
    assert len(overview["timeseries"]) == 7 and overview["timeseries"][-1]["queries"] == 3
    assert {"name": "faithfulness", "count": 1} in overview["failed_checks"]
    assert overview["top_documents"][0]["name"] == "handbook.pdf"
    assert sum(b["faithfulness"] for b in overview["score_distribution"]) == 3
