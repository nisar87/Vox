"""The live conversation client, exercised against a stand-in for Gemini's Live service."""

import base64
import json
import threading
import time

import pytest

pytest.importorskip("websockets")
np = pytest.importorskip("numpy")

from vox import live  # noqa: E402


class FakeGemini:
    """Speaks the server side of the Live protocol from a script."""

    def __init__(self, script):
        from websockets.sync.server import serve

        self.script, self.received, self.audio_bytes = script, [], 0
        self.server = serve(self.handle, "127.0.0.1", 0)
        self.port = self.server.socket.getsockname()[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def handle(self, ws):
        setup = json.loads(ws.recv())
        self.received.append(setup)
        ws.send(json.dumps({"setupComplete": {}}).encode())  # the real service sends binary frames
        stepper = iter(self.script)
        try:
            for raw in ws:
                message = json.loads(raw)
                if "realtimeInput" in message:
                    self.audio_bytes += len(base64.b64decode(message["realtimeInput"]["audio"]["data"]))
                    if self.audio_bytes >= 3200 and stepper is not None:
                        for out in next(stepper, []):
                            ws.send(json.dumps(out))
                        self.audio_bytes = 0
                else:
                    self.received.append(message)
                    for out in next(stepper, []):
                        ws.send(json.dumps(out))
        except Exception:
            pass

    def close(self):
        self.server.shutdown()


def run_session(monkeypatch, script, tool=None, feed_seconds=1.0, prefix=None):
    server = FakeGemini(script)
    monkeypatch.setattr(live, "URL", f"ws://127.0.0.1:{server.port}")
    monkeypatch.setattr(live, "IDLE_SECONDS", 3.0)
    events, calls = [], []

    def run_tool(name, args, heard):
        calls.append((name, args, heard))
        return (tool or (lambda n, a: {"ok": True, "message": "Done."}))(name, args)

    config = {"gemini_key": "k", "live_model": "gemini-3.8-live", "natural_voice": "", "patience": "1.4"}
    tools = live.declarations([{"name": "open_app", "description": "Open a program",
                                "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "more_steps": {"type": "boolean"}}, "required": ["name"]}},
                               {"name": "power", "description": "Power",
                                "parameters": {"type": "object", "properties": {"action": {"type": "string"}}, "required": ["action"]}}],
                              {"power"})
    session = live.LiveSession(config, "system text", tools, run_tool, lambda kind, **data: events.append((kind, data)), speak=False)
    chunk = b"\x01\x00" * live.CHUNK
    feed = [chunk] * int(feed_seconds * 10)
    real_sleep = time.sleep
    monkeypatch.setattr(live.time, "sleep", lambda s: real_sleep(min(s, 0.005) if s < 0.2 else s))
    session.run(feed=feed, prefix=prefix)
    server.close()
    return session, server, events, calls


def test_a_spoken_request_runs_a_skill_and_ends_politely(monkeypatch):
    audio = base64.b64encode(b"\x02\x00" * 480).decode()
    script = [
        [{"serverContent": {"inputTranscription": {"text": "Hi Vox, open "}}},
         {"serverContent": {"inputTranscription": {"text": "Notepad plus plus."}}},
         {"toolCall": {"functionCalls": [{"id": "f1", "name": "open_app", "args": {"name": "notepad++"}}]}}],
        # after the tool response:
        [{"serverContent": {"modelTurn": {"parts": [{"inlineData": {"mimeType": "audio/pcm;rate=24000", "data": audio}}]}}},
         {"serverContent": {"outputTranscription": {"text": "Opened."}}},
         {"serverContent": {"turnComplete": True}},
         {"serverContent": {"inputTranscription": {"text": "That's all, thanks."}}},
         {"toolCall": {"functionCalls": [{"id": "f2", "name": "end_conversation", "args": {}}]}}],
        [{"serverContent": {"outputTranscription": {"text": "Goodbye."}}}, {"serverContent": {"turnComplete": True}}],
    ]
    session, server, events, calls = run_session(monkeypatch, script)

    setup = server.received[0]["setup"]
    assert setup["model"] == "models/gemini-3.8-live"
    assert setup["generationConfig"]["responseModalities"] == ["AUDIO"]
    assert setup["realtimeInputConfig"]["automaticActivityDetection"]["endOfSpeechSensitivity"] == "END_SENSITIVITY_LOW"
    decls = {d["name"]: d for d in setup["tools"][0]["functionDeclarations"]}
    assert all(d["behavior"] == "NON_BLOCKING" for d in decls.values())
    assert "more_steps" not in decls["open_app"]["parameters"]["properties"]
    assert decls["power"]["parameters"]["properties"]["confirmed"]["type"] == "BOOLEAN"
    assert "end_conversation" in decls

    assert calls == [("open_app", {"name": "notepad++"}, "Hi Vox, open Notepad plus plus.")]
    responses = [m["toolResponse"]["functionResponses"][0] for m in server.received if "toolResponse" in m]
    assert responses[0] == {"id": "f1", "name": "open_app", "response": {"ok": True, "message": "Done."}}
    turns = [data for kind, data in events if kind == "turn"]
    assert turns[0]["heard"] == "Hi Vox, open Notepad plus plus." and turns[0]["reply"] == "Opened."
    assert turns[0]["steps"][0]["tool"] == "open_app"
    assert session.ended_by == "goodbye" and events[-1] == ("ended", {"why": "goodbye"})


def test_silence_ends_the_conversation_by_itself(monkeypatch):
    session, server, events, calls = run_session(monkeypatch, script=[], feed_seconds=0.3)
    assert session.ended_by == "quiet" and calls == []


def test_a_refused_setup_is_reported_in_plain_words(monkeypatch):
    from websockets.sync.server import serve

    def refuse(ws):
        ws.recv()
        ws.close(1008, "models/gemini-3.8-live is not found or not supported for bidiGenerateContent")

    server = serve(refuse, "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(live, "URL", f"ws://127.0.0.1:{server.socket.getsockname()[1]}")
    config = {"gemini_key": "k", "live_model": "gemini-3.8-live", "natural_voice": "", "patience": "1.4"}
    session = live.LiveSession(config, "s", [], lambda *a: {}, lambda *a, **k: None, speak=False)
    with pytest.raises(live.LiveError, match="not found or not supported"):
        session.run(feed=[])
    server.shutdown()


def test_risky_skills_need_a_spoken_yes_in_a_later_turn(vox, monkeypatch):
    from vox import app as app_module

    ran = []
    # Never run the real skill here: on Windows it would shut the machine down.
    monkeypatch.setattr(app_module, "run_tool", lambda name, args, ctx: ran.append((name, args)) or {"ok": True, "message": "Done."})
    state = app_module.VoxApp()
    args = {"action": "shutdown"}
    first = state._live_tool("power", dict(args), "shut down the pc")
    assert first["needs_confirmation"] and "Shut down the PC?" in first["message"]

    # The model may not approve its own request in the same turn...
    cheat = state._live_tool("power", {**args, "confirmed": True}, "shut down the pc")
    assert cheat["needs_confirmation"]
    # ...nor approve a different action than the one it asked about.
    state._live_turns += 1
    other = state._live_tool("power", {"action": "restart", "confirmed": True}, "yes")
    assert other["needs_confirmation"]
    assert ran == []

    state._live_tool("power", dict(args), "shut down the pc")
    state._live_turns += 1  # the user has spoken since the question
    done = state._live_tool("power", {**args, "confirmed": True}, "yes")
    assert done == {"ok": True, "message": "Done."} and ran == [("power", {"action": "shutdown"})]

    # Harmless skills run straight away.
    assert state._live_tool("open_website", {"site": "youtube"}, "open youtube")["ok"]
