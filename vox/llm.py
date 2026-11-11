"""The AI brain: Gemini and OpenAI behind one small interface.

Plain HTTPS with a kept-alive connection, so each command costs one request and
no connection setup. A Session holds one command's back-and-forth.
"""

from __future__ import annotations

import base64
import json

import httpx

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
TIMEOUT = httpx.Timeout(30.0, connect=6.0)
_NOT_CHAT = ("embedding", "tts", "transcribe", "whisper", "image", "moderation", "realtime",
             "audio", "sora", "dall-e", "imagen", "veo", "lyria", "live", "aqa", "robotics")


class LLMError(Exception):
    """A problem worth saying to the user in plain words."""


_client: httpx.Client | None = None


def client() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(timeout=TIMEOUT)
    return _client


def _check(response: httpx.Response, who: str) -> dict:
    if response.status_code == 200:
        return response.json()
    try:
        detail = response.json().get("error", {}).get("message", "")
    except ValueError:
        detail = response.text[:200]
    if response.status_code in (401, 403) or "API key" in detail:
        raise LLMError(f"{who} rejected the API key. Check it in Settings.")
    if response.status_code == 404:
        raise LLMError(f"{who} doesn't know that model. Pick another in Settings.")
    if response.status_code == 429:
        raise LLMError(f"{who} says the usage limit is reached. Try again shortly.")
    raise LLMError(f"{who} error {response.status_code}: {detail[:160]}")


def _post(url: str, headers: dict, body: dict, who: str) -> dict:
    try:
        return _check(client().post(url, headers=headers, json=body), who)
    except httpx.HTTPError as err:
        raise LLMError(f"I couldn't reach {who}. Check the internet connection. ({type(err).__name__})")


# ---------------------------------------------------------------- Gemini

def _gemini_schema(schema: dict) -> dict:
    """Gemini wants upper-case type names and a reduced JSON-schema vocabulary."""
    out = {}
    for key, value in schema.items():
        if key == "type":
            out[key] = value.upper()
        elif key == "properties":
            out[key] = {name: _gemini_schema(prop) for name, prop in value.items()}
        elif key == "items":
            out[key] = _gemini_schema(value)
        elif key in ("description", "enum", "required"):
            out[key] = value
    return out


class GeminiSession:
    who = "Gemini"

    def __init__(self, key: str, model: str, system: str, tools: list[dict]) -> None:
        self.key, self.model, self.system = key, model, system
        declarations = []
        for spec in tools:
            decl = {"name": spec["name"], "description": spec["description"]}
            if spec["parameters"]["properties"]:
                decl["parameters"] = _gemini_schema(spec["parameters"])
            declarations.append(decl)
        self.tools = [{"functionDeclarations": declarations}] if declarations else None
        self.contents: list[dict] = []

    def add_user(self, text: str) -> None:
        self.contents.append({"role": "user", "parts": [{"text": text}]})

    def step(self) -> tuple[str, list[dict]]:
        body = {"systemInstruction": {"parts": [{"text": self.system}]}, "contents": self.contents}
        if self.tools:
            body["tools"] = self.tools
        data = _post(f"{GEMINI_BASE}/models/{self.model}:generateContent",
                     {"x-goog-api-key": self.key}, body, self.who)
        candidates = data.get("candidates") or []
        if not candidates:
            raise LLMError("Gemini returned no answer for that request.")
        content = candidates[0].get("content") or {"role": "model", "parts": []}
        content.setdefault("role", "model")
        # Kept verbatim: newer models attach signatures that must be sent back.
        self.contents.append(content)
        text, calls = "", []
        for part in content.get("parts", []):
            if "functionCall" in part:
                fc = part["functionCall"]
                calls.append({"id": fc.get("id"), "name": fc["name"], "args": fc.get("args") or {}})
            elif part.get("text") and not part.get("thought"):
                text += part["text"]
        return text.strip(), calls

    def add_results(self, results: list[tuple[dict, dict]]) -> None:
        parts = []
        for call, result in results:
            response = {"name": call["name"], "response": result}
            if call.get("id"):
                response["id"] = call["id"]
            parts.append({"functionResponse": response})
        self.contents.append({"role": "user", "parts": parts})


# ---------------------------------------------------------------- OpenAI

class OpenAISession:
    who = "OpenAI"

    def __init__(self, key: str, model: str, system: str, tools: list[dict], base: str) -> None:
        self.key, self.model, self.base = key, model, base.rstrip("/")
        self.tools = [{"type": "function", "function": spec} for spec in tools]
        self.messages: list[dict] = [{"role": "system", "content": system}]

    def add_user(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})

    def step(self) -> tuple[str, list[dict]]:
        body = {"model": self.model, "messages": self.messages}
        if self.tools:
            body["tools"] = self.tools
        data = _post(f"{self.base}/chat/completions", {"Authorization": f"Bearer {self.key}"}, body, self.who)
        message = data["choices"][0]["message"]
        self.messages.append(message)
        calls = []
        for tc in message.get("tool_calls") or []:
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
            except ValueError:
                args = {}
            calls.append({"id": tc["id"], "name": tc["function"]["name"], "args": args})
        return (message.get("content") or "").strip(), calls

    def add_results(self, results: list[tuple[dict, dict]]) -> None:
        for call, result in results:
            self.messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result)})


# ---------------------------------------------------------------- shared

def ready(config) -> bool:
    provider = config["provider"]
    return bool(config[f"{provider}_key"] and config[f"{provider}_model"])


def session(config, system: str, tools: list[dict]):
    provider = config["provider"]
    if not config[f"{provider}_key"]:
        raise LLMError(f"Add your {provider.title()} API key in Settings so I can handle that.")
    if not config[f"{provider}_model"]:
        raise LLMError("Choose an AI model in Settings first.")
    if provider == "openai":
        return OpenAISession(config["openai_key"], config["openai_model"], system, tools, config["openai_base"])
    return GeminiSession(config["gemini_key"], config["gemini_model"], system, tools)


def list_models(provider: str, key: str, base: str = "https://api.openai.com/v1") -> list[str]:
    try:
        if provider == "openai":
            data = _check(client().get(f"{base.rstrip('/')}/models",
                                       headers={"Authorization": f"Bearer {key}"}), "OpenAI")
            names = [m["id"] for m in data.get("data", [])]
        else:
            data = _check(client().get(f"{GEMINI_BASE}/models", params={"pageSize": 200},
                                       headers={"x-goog-api-key": key}), "Gemini")
            names = [m["name"].removeprefix("models/") for m in data.get("models", [])
                     if "generateContent" in m.get("supportedGenerationMethods", [])]
    except httpx.HTTPError as err:
        raise LLMError(f"I couldn't reach {provider.title()}. ({type(err).__name__})")
    return sorted(n for n in names if not any(word in n.lower() for word in _NOT_CHAT))


def warm_up(config) -> None:
    """Open the HTTPS connection ahead of the first command."""
    try:
        url = config["openai_base"] if config["provider"] == "openai" else GEMINI_BASE
        client().get(url, timeout=5)
    except httpx.HTTPError:
        pass


def transcribe_openai(config, wav: bytes) -> str:
    try:
        response = client().post(
            f"{config['openai_base'].rstrip('/')}/audio/transcriptions",
            headers={"Authorization": f"Bearer {config['openai_key']}"},
            data={"model": config["openai_stt_model"], "language": "en"},
            files={"file": ("speech.wav", wav, "audio/wav")},
        )
    except httpx.HTTPError as err:
        raise LLMError(f"I couldn't reach OpenAI to transcribe. ({type(err).__name__})")
    return _check(response, "OpenAI").get("text", "").strip()


def transcribe_gemini(config, wav: bytes) -> str:
    body = {"contents": [{"role": "user", "parts": [
        {"inlineData": {"mimeType": "audio/wav", "data": base64.b64encode(wav).decode()}},
        {"text": "Transcribe this spoken command exactly. Reply with only the words spoken."},
    ]}]}
    data = _post(f"{GEMINI_BASE}/models/{config['gemini_model']}:generateContent",
                 {"x-goog-api-key": config["gemini_key"]}, body, "Gemini")
    parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
