"""Local web server behind the Vox window. Listens on 127.0.0.1 only."""

from __future__ import annotations

import asyncio
import secrets
import time
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from . import __version__, llm

UI = Path(__file__).parent / "ui" / "index.html"
ALLOWED_HOSTS = {"127.0.0.1", "localhost", "testserver"}


def create(app_state) -> FastAPI:
    api = FastAPI(title="Vox", docs_url=None, redoc_url=None, openapi_url=None)
    token = secrets.token_urlsafe(24)
    api.state.token = token

    @api.middleware("http")
    async def local_only(request: Request, call_next):
        # Blocks web pages that try to reach this server through a renamed host.
        host = (request.headers.get("host") or "").split(":")[0]
        if host not in ALLOWED_HOSTS:
            return HTMLResponse("Forbidden", status_code=403)
        return await call_next(request)

    def authed(x_vox_token: str = Header(default="")):
        if not secrets.compare_digest(x_vox_token, token):
            raise HTTPException(status_code=401, detail="Open Vox from its own window.")

    @api.get("/", response_class=HTMLResponse)
    def index():
        page = UI.read_text("utf-8").replace("{{TOKEN}}", token).replace("{{VERSION}}", __version__)
        return HTMLResponse(page, headers={"Cache-Control": "no-store"})

    @api.get("/api/state", dependencies=[Depends(authed)])
    def state():
        return app_state.snapshot()

    @api.post("/api/command", dependencies=[Depends(authed)])
    def command(body: dict):
        return app_state.run_text(str(body.get("text", "")))

    @api.post("/api/listen", dependencies=[Depends(authed)])
    def listen():
        if not app_state.snapshot()["parts"]["microphone"]:
            raise HTTPException(400, "The microphone library isn't installed. Run install.bat.")
        app_state.listen()
        return {"ok": True}

    @api.post("/api/undo", dependencies=[Depends(authed)])
    def undo():
        return app_state.undo()

    @api.post("/api/settings", dependencies=[Depends(authed)])
    def settings(body: dict):
        try:
            app_state.apply_settings(body)
        except (TypeError, ValueError) as err:
            raise HTTPException(400, f"That setting isn't valid: {err}")
        return app_state.snapshot()

    @api.post("/api/models", dependencies=[Depends(authed)])
    def models(body: dict):
        provider = "openai" if body.get("provider") == "openai" else "gemini"
        key = body.get("key") or app_state.config[f"{provider}_key"]
        if not key:
            raise HTTPException(400, "Enter the API key first.")
        try:
            return {"models": llm.list_models(provider, key, body.get("base") or app_state.config["openai_base"])}
        except llm.LLMError as err:
            raise HTTPException(400, str(err))

    @api.post("/api/test", dependencies=[Depends(authed)])
    def test():
        """One tiny request to the chosen model, to prove the key works and time it."""
        try:
            session = llm.session(app_state.config, "Reply with the single word: ready", [])
            session.add_user("Are you there?")
            started = time.perf_counter()
            reply, _ = session.step()
        except llm.LLMError as err:
            raise HTTPException(400, str(err))
        return {"reply": reply, "ms": round((time.perf_counter() - started) * 1000)}

    @api.post("/api/learned/forget", dependencies=[Depends(authed)])
    def forget(body: dict):
        if body.get("all"):
            app_state.memory.clear()
        else:
            app_state.memory.forget(str(body.get("id", "")))
        return app_state.memory.listing()

    @api.post("/api/update/check", dependencies=[Depends(authed)])
    def update_check():
        return app_state.check_update()

    @api.post("/api/update/install", dependencies=[Depends(authed)])
    def update_install():
        result = app_state.install_update()
        if not result["ok"]:
            raise HTTPException(400, result["message"])
        return result

    @api.get("/api/voices", dependencies=[Depends(authed)])
    def voices():
        return {"voices": app_state.speaker.voices()}

    @api.websocket("/ws")
    async def live(ws: WebSocket):
        if not secrets.compare_digest(ws.query_params.get("token", ""), token):
            await ws.close(code=4401)
            return
        await ws.accept()
        loop, q = asyncio.get_running_loop(), asyncio.Queue(maxsize=500)
        app_state.bus.subscribe(loop, q)
        try:
            while True:
                await ws.send_json(await q.get())
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            app_state.bus.unsubscribe(loop, q)

    return api
