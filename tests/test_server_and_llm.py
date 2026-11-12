import httpx
import pytest
from fastapi.testclient import TestClient

from vox import llm


@pytest.fixture
def client(vox, monkeypatch):
    from vox import app as app_module
    from vox import server

    state = app_module.VoxApp()
    api = server.create(state)
    c = TestClient(api)
    c.headers["X-Vox-Token"] = api.state.token
    c.vox = state
    return c


def test_page_loads_and_api_needs_the_token(client):
    assert "Vox" in client.get("/").text
    assert client.get("/api/state", headers={"X-Vox-Token": "wrong"}).status_code == 401
    assert client.get("/api/state", headers={"Host": "evil.example"}).status_code == 403


def test_keys_are_never_sent_back(client):
    client.post("/api/settings", json={"gemini_key": "AIza-secret-key-1234", "browser": "edge"})
    body = client.get("/api/state").text
    assert "AIza-secret" not in body
    settings = client.get("/api/state").json()["settings"]
    assert settings["gemini_key_set"] and settings["gemini_key_hint"] == "…1234" and settings["browser"] == "edge"
    client.post("/api/settings", json={"gemini_key": ""})  # blank keeps the saved key
    assert client.vox.config["gemini_key"] == "AIza-secret-key-1234"


def test_command_over_http_and_live_event(client):
    with client.websocket_connect(f"/ws?token={client.app.state.token}") as ws:
        result = client.post("/api/command", json={"text": "search for cats on youtube"}).json()
        assert result["path"] == "instant" and result["ok"]
        kinds = [ws.receive_json()["type"] for _ in range(3)]
        assert kinds == ["state", "state", "result"]
    assert client.get("/api/state").json()["history"][0]["heard"] == "search for cats on youtube"


def fake_http(monkeypatch, handler):
    seen = []

    def wrapped(request):
        seen.append(request)
        return handler(request)

    monkeypatch.setattr(llm, "_client", httpx.Client(transport=httpx.MockTransport(wrapped)))
    return seen


TOOLS = [{"name": "open_app", "description": "Open a program",
          "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
         {"name": "system_status", "description": "PC status",
          "parameters": {"type": "object", "properties": {}, "required": []}}]


def test_gemini_round_trip(monkeypatch):
    import json

    replies = [
        {"candidates": [{"content": {"role": "model", "parts": [
            {"functionCall": {"name": "open_app", "args": {"name": "notepad"}, "id": "f1"}, "thoughtSignature": "sig"}]}}]},
        {"candidates": [{"content": {"role": "model", "parts": [{"text": "Opened."}]}}]},
    ]
    seen = fake_http(monkeypatch, lambda request: httpx.Response(200, json=replies.pop(0)))
    session = llm.GeminiSession("k", "gemini-flash-latest", "sys", TOOLS)
    session.add_user("open notepad")
    text, calls = session.step()
    assert calls == [{"id": "f1", "name": "open_app", "args": {"name": "notepad"}}]
    session.add_results([(calls[0], {"ok": True, "message": "Opening Notepad."})])
    assert session.step() == ("Opened.", [])

    first, second = (json.loads(r.content) for r in seen)
    assert seen[0].headers["x-goog-api-key"] == "k" and "gemini-flash-latest:generateContent" in str(seen[0].url)
    decls = first["tools"][0]["functionDeclarations"]
    assert decls[0]["parameters"]["type"] == "OBJECT" and decls[0]["parameters"]["properties"]["name"]["type"] == "STRING"
    assert "parameters" not in decls[1]  # tools without arguments send no schema
    assert "temperature" not in json.dumps(first)
    assert first["generationConfig"]["thinkingConfig"]["thinkingLevel"] == "minimal"
    assert second["contents"][1]["parts"][0]["thoughtSignature"] == "sig"  # sent back untouched
    assert second["contents"][2]["parts"][0]["functionResponse"]["id"] == "f1"


def test_openai_round_trip(monkeypatch):
    import json

    replies = [
        {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
            {"id": "call_1", "type": "function", "function": {"name": "open_app", "arguments": '{"name": "excel"}'}}]}}]},
        {"choices": [{"message": {"role": "assistant", "content": "Excel is open."}}]},
    ]
    seen = fake_http(monkeypatch, lambda request: httpx.Response(200, json=replies.pop(0)))
    session = llm.OpenAISession("sk", "some-model", "sys", TOOLS, "https://api.openai.com/v1/")
    session.add_user("open excel")
    _, calls = session.step()
    assert calls[0]["args"] == {"name": "excel"}
    session.add_results([(calls[0], {"ok": True})])
    assert session.step() == ("Excel is open.", [])
    body = json.loads(seen[1].content)
    assert str(seen[1].url) == "https://api.openai.com/v1/chat/completions"
    assert body["messages"][-1] == {"role": "tool", "tool_call_id": "call_1", "content": '{"ok": true}'}


def test_errors_become_plain_sentences(monkeypatch):
    fake_http(monkeypatch, lambda request: httpx.Response(400, json={"error": {"message": "API key not valid."}}))
    session = llm.GeminiSession("bad", "m", "sys", [])
    session.add_user("hi")
    with pytest.raises(llm.LLMError, match="rejected the API key"):
        session.step()


def test_model_list_hides_non_chat_models(monkeypatch):
    fake_http(monkeypatch, lambda request: httpx.Response(200, json={"models": [
        {"name": "models/gemini-flash-latest", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-embedding-001", "supportedGenerationMethods": ["embedContent"]},
        {"name": "models/gemini-3.8-flash-tts", "supportedGenerationMethods": ["generateContent"]}]}))
    assert llm.list_models("gemini", "k") == ["gemini-flash-latest"]


def test_window_has_no_duplicate_ids():
    """Two elements sharing an id once made the API key box silently unusable."""
    import collections
    import re
    from pathlib import Path

    html = (Path(__file__).parent.parent / "vox" / "ui" / "index.html").read_text("utf-8")
    counts = collections.Counter(re.findall(r'\bid="([^"]+)"', html))
    assert [name for name, n in counts.items() if n > 1] == []
    used = set(re.findall(r'\$\("([^"]+)"\)', html))
    assert used - set(counts) == set(), "script refers to ids that do not exist"


def test_models_without_a_thinking_setting_are_retried_plainly(monkeypatch):
    import json

    bodies = []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        if "generationConfig" in body:
            return httpx.Response(400, json={"error": {"message": "Unknown name thinkingLevel"}})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "ok"}]}}]})

    fake_http(monkeypatch, handler)
    monkeypatch.setattr(llm, "_no_thinking_setting", set())
    for _ in range(2):
        session = llm.GeminiSession("k", "old-model", "sys", [])
        session.add_user("hi")
        assert session.step() == ("ok", [])
    assert ["generationConfig" in b for b in bodies] == [True, False, False]  # learned after one refusal


def test_natural_voice_request_and_cache(vox, monkeypatch):
    import base64
    import json

    from vox import voice

    pcm = b"\x01\x00" * 2400
    seen = []

    def handler(request):
        seen.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"models": [
                {"name": "models/gemini-3.8-flash-tts", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/gemini-3.8-flash-lite-tts", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/gemini-3.5-flash-lite", "supportedGenerationMethods": ["generateContent"]}]})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"inlineData": {
            "mimeType": "audio/L16;codec=pcm;rate=24000", "data": base64.b64encode(pcm).decode()}}]}}]})

    fake_http(monkeypatch, handler)
    monkeypatch.setattr(llm, "_tts_model", {})
    vox.config.update({"gemini_key": "k", "natural_voice": "Charon"})
    assert voice.natural_audio(vox.config, "Yes Nisar, I'm listening.") == (pcm, 24000)
    assert voice.natural_audio(vox.config, "Yes Nisar, I'm listening.") == (pcm, 24000)
    posts = [r for r in seen if r.method == "POST"]
    assert len(posts) == 1, "the second time must come from the cache, with no request"
    assert "gemini-3.8-flash-lite-tts:generateContent" in str(posts[0].url)
    body = json.loads(posts[0].content)
    assert body["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Charon"
