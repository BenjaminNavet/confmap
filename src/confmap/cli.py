"""Point d'entrée : `confmap serve [--audio-file F] [--speed S] [--config C]`."""

from __future__ import annotations

import argparse
import logging
import socket
import sys
from pathlib import Path

from dotenv import load_dotenv


def build_services(config_path: Path | None, audio_file: Path | None, speed: float):
    """Assemble les vraies dépendances de l'application."""
    from confmap.audio import FileSource, MicrophoneSource
    from confmap.config import load_settings
    from confmap.llm import ClaudeCliClient
    from confmap.segmenter import SileroDetector
    from confmap.session_store import SessionStore
    from confmap.transcriber import create_transcriber
    from confmap.web.app import AppServices

    settings = load_settings(config_path)

    def audio_source_factory():
        if audio_file is not None:
            return FileSource(audio_file, speed=speed)
        return MicrophoneSource()

    return AppServices(
        settings=settings,
        store=SessionStore(settings.paths.sessions),
        llm=ClaudeCliClient(),
        transcriber=create_transcriber(
            settings.models.whisper_live, settings.models.whisper_fallback
        ),
        detector_factory=SileroDetector,
        audio_source_factory=audio_source_factory,
    )


def port_in_use(port: int) -> bool:
    """Indique si un serveur écoute déjà sur ce port en local."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def main() -> None:
    """Lance le serveur."""
    parser = argparse.ArgumentParser(prog="confmap")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="lancer le serveur web")
    serve.add_argument("--config", type=Path, default=None)
    serve.add_argument(
        "--audio-file",
        type=Path,
        default=None,
        help="rejouer un fichier au lieu du micro",
    )
    serve.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="vitesse de relecture du fichier (0 = max)",
    )
    serve.add_argument("--port", type=int, default=None)
    serve.add_argument(
        "--no-warmup", action="store_true", help="ne pas précharger Whisper"
    )
    args = parser.parse_args()

    load_dotenv()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    import asyncio

    import uvicorn

    from confmap.web.app import create_app

    services = build_services(args.config, args.audio_file, args.speed)
    if args.port:
        services.settings.server.port = args.port
    port = services.settings.server.port
    if port_in_use(port):
        # Déjà lancé (Spotlight, autre terminal) : inutile de charger Whisper pour échouer ensuite.
        print(f"confmap tourne déjà : http://localhost:{port}")
        sys.exit(0)
    if not args.no_warmup:
        logging.getLogger("confmap").info(
            "chargement de Whisper (%s)…", services.settings.models.whisper_live
        )
        asyncio.run(services.transcriber.warm_up())
    app = create_app(services)
    print(f"confmap : http://localhost:{services.settings.server.port}")
    uvicorn.run(
        app,
        host=services.settings.server.host,
        port=services.settings.server.port,
        log_level="warning",
    )
