import pytest
from conftest import FakeDetector, FakeLlm, FakeTranscriber, png_bytes
from fastapi.testclient import TestClient

from confmap.audio import FileSource
from confmap.config import Settings
from confmap.web.app import AppServices, create_app


@pytest.fixture
def services(store, speech_wav, tmp_path):
    settings = Settings()
    settings.map.interval_seconds = 0.2
    settings.map.min_gap_seconds = 0
    settings.paths.vault = tmp_path / "vault"
    return AppServices(
        settings=settings,
        store=store,
        llm=FakeLlm(),
        transcriber=FakeTranscriber(),
        detector_factory=FakeDetector,
        audio_source_factory=lambda: FileSource(speech_wav, speed=0),
    )


@pytest.fixture
def client(services):
    with TestClient(create_app(services)) as test_client:
        yield test_client


def test_session_lifecycle(client, services):
    created = client.post("/api/sessions")
    assert created.status_code == 200
    session_id = created.json()["id"]
    token = services.store.load(session_id).meta.token
    assert created.json()["recording"] is True
    assert f"s={session_id}&t={token}" in created.json()["capture_url"]

    assert client.post("/api/sessions").status_code == 409

    listing = client.get("/api/sessions").json()
    assert [s["id"] for s in listing] == [session_id]

    response = client.post(
        f"/api/sessions/{session_id}/context", json={"title": "Titre", "speaker": "Ada"}
    )
    assert response.status_code == 200
    assert client.get(f"/api/sessions/{session_id}").json()["title"] == "Titre"

    note = client.post(f"/api/sessions/{session_id}/notes", json={"text": "  ma note "})
    assert note.status_code == 200 and note.json()["id"]
    assert (
        client.post(
            f"/api/sessions/{session_id}/notes", json={"text": "  "}
        ).status_code
        == 400
    )
    slides = client.get(f"/api/sessions/{session_id}/slides").json()
    assert [(item["kind"], item["text"]) for item in slides] == [("note", "ma note")]

    assert client.get("/api/sessions/inconnue").status_code == 404


def test_websocket_snapshot_contains_context(client):
    session_id = client.post("/api/sessions").json()["id"]
    client.post(
        f"/api/sessions/{session_id}/context", json={"title": "WS", "speaker": ""}
    )
    with client.websocket_connect(f"/ws/{session_id}") as websocket:
        message = websocket.receive_json()
    assert message["type"] == "snapshot"
    contexts = [e for e in message["events"] if e["type"] == "context"]
    assert contexts and contexts[0]["title"] == "WS"


def test_photo_upload_with_token(client, services):
    session_id = client.post("/api/sessions").json()["id"]
    token = services.store.load(session_id).meta.token
    response = client.post(
        f"/api/sessions/{session_id}/photos?t={token}",
        files={"file": ("slide.png", png_bytes(), "image/png")},
    )
    assert response.status_code == 200 and response.json()["id"]
    assert (
        client.post(
            f"/api/sessions/{session_id}/photos",
            files={"file": ("empty.png", b"", "image/png")},
        ).status_code
        == 400
    )


def test_remote_client_needs_token(services):
    app = create_app(services)
    try:
        remote = TestClient(app, client=("192.168.1.20", 1234))
    except TypeError:
        pytest.skip("cette version de Starlette n'accepte pas l'argument client")
    session = services.store.create()
    url = f"/api/sessions/{session.id}/notes"
    assert remote.post(url, json={"text": "x"}).status_code == 403
    assert remote.post(f"{url}?t=mauvais", json={"text": "x"}).status_code == 403
    ok = remote.post(f"{url}?t={session.meta.token}", json={"text": "depuis iPhone"})
    assert ok.status_code == 200
    assert services.runtimes[session.id].state.notes[0].origin == "iphone"
    # les routes réservées au Mac restent fermées même avec le jeton
    assert remote.get("/api/sessions").status_code == 403
    assert remote.post(f"/api/sessions/{session.id}/stop").status_code == 403


def test_qr_and_pages(client):
    session_id = client.post("/api/sessions").json()["id"]
    qr = client.get(f"/api/sessions/{session_id}/qr.svg")
    assert qr.status_code == 200
    assert qr.headers["content-type"].startswith("image/svg+xml")
    assert b"<svg" in qr.content

    for path in ("/", "/capture"):
        page = client.get(path)
        assert page.status_code == 200
        assert "text/html" in page.headers["content-type"]


async def test_stop_finalizes_into_vault(services):
    # la finalisation tourne dans la boucle du serveur : on utilise le TestClient en contexte
    with TestClient(create_app(services)) as client:
        session_id = client.post("/api/sessions").json()["id"]
        client.post(
            f"/api/sessions/{session_id}/context", json={"title": "Fin", "speaker": ""}
        )
        assert client.post(f"/api/sessions/{session_id}/stop").status_code == 200
        session = services.store.load(session_id)
        import time

        deadline = time.monotonic() + 15
        while not session.is_finalized() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert session.is_finalized()
        assert list(services.settings.paths.vault.rglob("*.md"))
        assert client.get(f"/api/sessions/{session_id}").json()["finalized"] is True
