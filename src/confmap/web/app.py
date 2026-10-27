"""Serveur FastAPI : interface Mac, page iPhone, API REST et WebSocket."""

from __future__ import annotations

import asyncio
import contextlib
import io
import logging
import socket
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated

import qrcode
import qrcode.image.svg
from fastapi import (
    Depends,
    FastAPI,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from confmap.audio import AudioSource
from confmap.config import Settings
from confmap.events import FinalizeStepEvent
from confmap.finalizer import Finalizer
from confmap.llm import LlmClient
from confmap.runtime import SessionRuntime
from confmap.segmenter import SpeechDetector
from confmap.session_store import SessionLog, SessionStore
from confmap.transcriber import Transcriber

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}
MAX_PHOTO_BYTES = 15 * 1024 * 1024


@dataclass
class AppServices:
    """Dépendances injectées (remplacées par des faux objets dans les tests)."""

    settings: Settings
    store: SessionStore
    llm: LlmClient
    transcriber: Transcriber
    detector_factory: Callable[[], SpeechDetector]
    audio_source_factory: Callable[[], AudioSource]
    runtimes: dict[str, SessionRuntime] = field(default_factory=dict)
    finalize_tasks: dict[str, asyncio.Task] = field(default_factory=dict)

    def runtime(self, session_id: str) -> SessionRuntime:
        """Runtime de la session (créé à la demande)."""
        if session_id not in self.runtimes:
            try:
                session = self.store.load(session_id)
            except KeyError as error:
                raise HTTPException(404, "session inconnue") from error
            self.runtimes[session_id] = SessionRuntime(
                session,
                self.settings,
                self.llm,
                self.transcriber,
                self.detector_factory,
            )
        return self.runtimes[session_id]

    def recording_session_id(self) -> str | None:
        """Session en cours d'enregistrement, s'il y en a une."""
        return next(
            (sid for sid, runtime in self.runtimes.items() if runtime.capturing), None
        )


class ContextBody(BaseModel):
    """Titre et orateur."""

    title: str = ""
    speaker: str = ""


class NoteBody(BaseModel):
    """Note libre."""

    text: str


class PositionsBody(BaseModel):
    """Positions des nœuds affichés."""

    positions: dict[str, tuple[float, float]]


def lan_ip() -> str:
    """Adresse IP du Mac sur le réseau local (aucun paquet n'est envoyé)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        try:
            probe.connect(("10.255.255.255", 1))
            return probe.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def session_summary(
    services: AppServices, session: SessionLog, request_base: str
) -> dict:
    """Description d'une session pour l'interface."""
    runtime = services.runtimes.get(session.id)
    state_title = ""
    for event in reversed(session.events):
        if event.type == "context":
            state_title = event.title
            break
    last_steps = {}
    for event in session.events:
        if isinstance(event, FinalizeStepEvent):
            last_steps[event.step] = event.state
    return {
        "id": session.id,
        "title": state_title,
        "created_at": session.meta.created_at,
        "recording": bool(runtime and runtime.capturing),
        "elapsed": runtime.now() if runtime else 0.0,
        "finalized": session.is_finalized(),
        "finalizing": session.id in services.finalize_tasks
        and not services.finalize_tasks[session.id].done(),
        "finalize_steps": last_steps,
        "capture_url": f"{request_base}/capture?s={session.id}&t={session.meta.token}",
    }


def local_only(request: Request) -> None:
    """Dépendance : réserve la route aux clients locaux (le Mac)."""
    host = request.client.host if request.client else ""
    if host not in LOCAL_HOSTS:
        raise HTTPException(403, "réservé au Mac")


# Défini au niveau du module : avec `from __future__ import annotations`, FastAPI
# doit pouvoir résoudre cet alias depuis les globals du module.
LocalOnly = Annotated[None, Depends(local_only)]

ALLOWED_HOSTNAMES = {"localhost", "127.0.0.1", "[::1]", "testserver"}


def is_allowed_host(host_header: str, port: int) -> bool:
    """Vrai si l'en-tête Host (ou Origin sans schéma) vise bien ce serveur.

    Protège contre le DNS rebinding : un nom de domaine étranger qui résoudrait vers le Mac.
    """
    if not host_header:
        return False
    hostname, _, host_port = (
        host_header.rpartition(":")
        if not host_header.endswith("]")
        else (host_header, "", "")
    )
    if not hostname:  # pas de port
        hostname, host_port = host_header, ""
    if host_port and host_port != str(port) and hostname != "testserver":
        return False
    return hostname in ALLOWED_HOSTNAMES or hostname == lan_ip()


class SameOriginMiddleware:
    """Refuse les requêtes venant d'un autre site (CSRF, WebSocket détourné, DNS rebinding)."""

    def __init__(self, app, port: int) -> None:
        """Enveloppe l'application ASGI."""
        self.app = app
        self.port = port

    async def __call__(self, scope, receive, send) -> None:
        """Vérifie Host et Origin avant de transmettre la requête."""
        if scope["type"] in ("http", "websocket"):
            headers = {
                key.decode("latin-1"): value.decode("latin-1")
                for key, value in scope.get("headers", [])
            }
            origin = headers.get("origin", "")
            origin_host = (
                origin.split("://", 1)[-1] if origin and origin != "null" else ""
            )
            allowed = is_allowed_host(headers.get("host", ""), self.port) and (
                not origin or (origin_host and is_allowed_host(origin_host, self.port))
            )
            if not allowed:
                if scope["type"] == "websocket":
                    await send({"type": "websocket.close", "code": 4403})
                    return
                response = Response("origine refusée", status_code=403)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def create_app(services: AppServices) -> FastAPI:
    """Construit l'application web."""

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        for runtime in services.runtimes.values():
            with contextlib.suppress(Exception):
                await runtime.shutdown()

    app = FastAPI(title="confmap", lifespan=lifespan)
    app.state.services = services
    app.add_middleware(SameOriginMiddleware, port=services.settings.server.port)

    @app.middleware("http")
    async def no_stale_frontend(request: Request, call_next):
        # Le navigateur revalide toujours l'interface : une mise à jour est vue au rechargement.
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith(
            ("/static", "/capture")
        ):
            response.headers["Cache-Control"] = "no-cache"
        return response

    def capture_base() -> str:
        return f"http://{lan_ip()}:{services.settings.server.port}"

    def authorize(request: Request, session_id: str, token: str | None) -> SessionLog:
        """Les clients non locaux (iPhone) doivent fournir le jeton de la session."""
        try:
            session = services.store.load(session_id)
        except KeyError as error:
            raise HTTPException(404, "session inconnue") from error
        host = request.client.host if request.client else ""
        if host not in LOCAL_HOSTS and token != session.meta.token:
            raise HTTPException(403, "jeton invalide")
        return session

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/capture")
    async def capture_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "capture.html")

    @app.get("/favicon.ico")
    async def favicon() -> Response:
        return Response(status_code=204)

    @app.get("/api/sessions")
    async def list_sessions(_: LocalOnly) -> list[dict]:
        base = capture_base()
        return [
            session_summary(services, services.store.load(sid), base)
            for sid in services.store.list_ids()[:50]
        ]

    @app.post("/api/sessions")
    async def create_session(_: LocalOnly) -> dict:
        if services.recording_session_id():
            raise HTTPException(409, "une session enregistre déjà")
        session = services.store.create()
        runtime = services.runtime(session.id)
        runtime.start_recording(services.audio_source_factory())
        return session_summary(services, session, capture_base())

    @app.get("/api/sessions/{session_id}")
    async def get_session(session_id: str, _: LocalOnly) -> dict:
        runtime = services.runtime(session_id)
        return session_summary(services, runtime.session, capture_base())

    @app.post("/api/sessions/{session_id}/resume")
    async def resume_session(session_id: str, _: LocalOnly) -> dict:
        other = services.recording_session_id()
        if other and other != session_id:
            raise HTTPException(409, "une autre session enregistre déjà")
        runtime = services.runtime(session_id)
        if runtime.session.is_finalized():
            raise HTTPException(409, "session déjà finalisée")
        await runtime.resume(services.audio_source_factory())
        return session_summary(services, runtime.session, capture_base())

    @app.post("/api/sessions/{session_id}/pause")
    async def pause_session(session_id: str, _: LocalOnly) -> dict:
        runtime = services.runtime(session_id)
        runtime.pause()
        return session_summary(services, runtime.session, capture_base())

    @app.post("/api/sessions/{session_id}/context")
    async def set_context(session_id: str, body: ContextBody, _: LocalOnly) -> dict:
        services.runtime(session_id).set_context(body.title, body.speaker)
        return {"ok": True}

    @app.post("/api/sessions/{session_id}/notes")
    async def add_note(
        request: Request, session_id: str, body: NoteBody, t: str | None = Query(None)
    ) -> dict:
        authorize(request, session_id, t)
        text = body.text.strip()
        if not text:
            raise HTTPException(400, "note vide")
        host = request.client.host if request.client else ""
        note = services.runtime(session_id).add_note(
            text[:4000], origin="mac" if host in LOCAL_HOSTS else "iphone"
        )
        return {"id": note.id}

    @app.post("/api/sessions/{session_id}/photos")
    async def add_photo(
        request: Request,
        session_id: str,
        file: Annotated[UploadFile, File()],
        t: str | None = Query(None),
    ) -> dict:
        authorize(request, session_id, t)
        raw = await file.read(MAX_PHOTO_BYTES + 1)
        if len(raw) > MAX_PHOTO_BYTES:
            raise HTTPException(413, "photo trop lourde (15 Mo max)")
        if not raw:
            raise HTTPException(400, "photo vide")
        slide = services.runtime(session_id).add_photo(raw)
        return {"id": slide.id}

    @app.get("/api/sessions/{session_id}/slides")
    async def list_slides(
        request: Request, session_id: str, t: str | None = Query(None)
    ) -> list[dict]:
        authorize(request, session_id, t)
        state = services.runtime(session_id).state
        notes = [
            {"id": n.id, "kind": "note", "status": "done", "text": n.text, "ts": n.ts}
            for n in state.notes
        ]
        slides = [
            {
                "id": s.id,
                "kind": "slide",
                "status": s.status,
                "text": s.text_fr,
                "ts": s.ts,
            }
            for s in state.slides.values()
        ]
        return sorted(notes + slides, key=lambda item: item["ts"], reverse=True)[:20]

    @app.post("/api/sessions/{session_id}/map/force")
    async def force_map(session_id: str, _: LocalOnly) -> dict:
        services.runtime(session_id).force_map()
        return {"ok": True}

    @app.post("/api/sessions/{session_id}/map/positions")
    async def set_positions(session_id: str, body: PositionsBody, _: LocalOnly) -> dict:
        services.runtime(session_id).set_positions(body.positions)
        return {"ok": True}

    async def run_finalization(runtime: SessionRuntime) -> None:
        if runtime.recording:
            await runtime.stop_recording()
        await runtime.drain()
        await Finalizer(runtime, services.settings.paths.vault).run()

    def launch_finalization(session_id: str) -> None:
        task = services.finalize_tasks.get(session_id)
        if task and not task.done():
            return
        services.finalize_tasks[session_id] = asyncio.ensure_future(
            run_finalization(services.runtime(session_id))
        )

    @app.post("/api/sessions/{session_id}/stop")
    async def stop_session(session_id: str, _: LocalOnly) -> dict:
        services.runtime(session_id).release_microphone()
        launch_finalization(session_id)
        return {"ok": True}

    @app.post("/api/sessions/{session_id}/finalize")
    async def finalize_session(session_id: str, _: LocalOnly) -> dict:
        runtime = services.runtime(session_id)
        runtime.start_workers()
        launch_finalization(session_id)
        return {"ok": True}

    @app.get("/api/sessions/{session_id}/qr.svg")
    async def qr_code(session_id: str, _: LocalOnly) -> Response:
        session = services.runtime(session_id).session
        url = f"{capture_base()}/capture?s={session.id}&t={session.meta.token}"
        image = qrcode.make(
            url, image_factory=qrcode.image.svg.SvgPathImage, box_size=12
        )
        buffer = io.BytesIO()
        image.save(buffer)
        return Response(buffer.getvalue(), media_type="image/svg+xml")

    @app.websocket("/ws/{session_id}")
    async def session_stream(websocket: WebSocket, session_id: str) -> None:
        host = websocket.client.host if websocket.client else ""
        if host not in LOCAL_HOSTS:
            await websocket.close(code=4403)
            return
        try:
            runtime = services.runtime(session_id)
        except HTTPException:
            await websocket.close(code=4404)
            return
        await websocket.accept()
        queue = runtime.session.bus.subscribe()
        try:
            snapshot = [
                event.model_dump(mode="json") for event in runtime.session.events
            ]
            await websocket.send_json({"type": "snapshot", "events": snapshot})
            receiver = asyncio.ensure_future(websocket.receive_text())
            while True:
                getter = asyncio.ensure_future(queue.get())
                done, _ = await asyncio.wait(
                    {getter, receiver}, return_when=asyncio.FIRST_COMPLETED
                )
                if (
                    receiver in done
                ):  # le client s'est déconnecté (il n'envoie rien d'autre)
                    getter.cancel()
                    receiver.result()
                    receiver = asyncio.ensure_future(websocket.receive_text())
                    continue
                await websocket.send_json(getter.result().model_dump(mode="json"))
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            runtime.session.bus.unsubscribe(queue)
            with contextlib.suppress(Exception):
                receiver.cancel()

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/s/{session_id}")
    async def session_shortcut(session_id: str) -> RedirectResponse:
        return RedirectResponse(f"/?s={session_id}")

    return app
