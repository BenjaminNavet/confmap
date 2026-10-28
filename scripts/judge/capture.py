"""Banc de test du juge : rejoue un extrait audio, pilote l'UI en headless, rend la sortie Obsidian.

Usage (depuis la racine du dépôt) :
    uv run --with playwright --with markdown python scripts/judge/capture.py .judge/iter-1

Produit dans le dossier de sortie : captures de l'UI (desktop clair/sombre, iPhone),
la note et le canvas générés, les diagrammes Mermaid rendus (mmdc) et un rendu PNG du canvas.
Rien ne s'ouvre au premier plan.
"""

import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "scripts/judge/config.toml"
AUDIO = ROOT / ".judge/extrait.wav"
JUDGE_DIR = ROOT / ".judge"
PORT = 8011
BASE = f"http://127.0.0.1:{PORT}"
REPLAY_SECONDS = 95
SLIDE_HTML = """<html><body style="margin:0;width:1280px;height:720px;background:#fff;font:28px Helvetica;padding:50px;box-sizing:border-box">
<h1 style="font-size:52px;margin:0 0 30px">Knowledge Graphs in industry: 2018 vs 2026</h1>
<ul><li>2018: Google, Microsoft, Amazon, Facebook, eBay, IBM</li>
<li>2026: + Huawei, Tencent, Alibaba, IKEA, Siemens, Bosch</li>
<li>Ontologies and knowledge graphs across all areas of society and the economy</li></ul>
<p style="color:#888">ISWC 2026 keynote</p></body></html>"""


def make_slide(browser, path: Path) -> None:
    """Fabrique une photo de slide de démonstration (texte lisible par la vision)."""
    page = browser.new_page(viewport={"width": 1280, "height": 720})
    page.set_content(SLIDE_HTML)
    page.screenshot(path=path)
    page.close()


def start_server(log_path: Path) -> subprocess.Popen:
    """Lance confmap sur le port du juge avec un vault et des sessions isolés."""
    for name in ("vault", "sessions"):
        shutil.rmtree(JUDGE_DIR / name, ignore_errors=True)
    log = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        [
            "uv",
            "run",
            "confmap",
            "serve",
            "--config",
            str(CONFIG),
            "--audio-file",
            str(AUDIO),
            "--speed",
            "1",
        ],
        cwd=ROOT,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    deadline = time.time() + 300
    while time.time() < deadline:
        try:
            import urllib.request

            urllib.request.urlopen(BASE + "/api/sessions", timeout=2)
            return process
        except OSError:
            time.sleep(2)
    process.kill()
    raise RuntimeError("serveur non démarré, voir " + str(log_path))


def capture_ui(out: Path) -> None:
    """Déroule une session complète dans Chromium headless et prend des captures."""
    shots = out / "ui"
    shots.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 1440, "height": 900}, color_scheme="dark"
        )
        console: list[str] = []
        page.on(
            "console", lambda message: console.append(f"{message.type}: {message.text}")
        )
        page.goto(BASE)
        page.wait_for_timeout(1500)
        page.screenshot(path=shots / "00-accueil.png")
        page.click("#newBtn")
        page.fill("#titleInput", "It was never about the web: rethinking semantics")
        page.fill("#speakerInput", "Keynote")
        page.press("#speakerInput", "Enter")
        started = time.time()
        index = 1
        noted = False
        slide_sent = False
        page.click("#qrBtn")
        page.wait_for_timeout(800)
        capture_url = re.sub(
            r"^https?://[^/]+", BASE, page.get_attribute("#captureLink", "href") or ""
        )
        page.keyboard.press("Escape")
        while time.time() - started < REPLAY_SECONDS:
            page.wait_for_timeout(15000)
            page.screenshot(
                path=shots / f"{index:02d}-direct-{int(time.time() - started)}s.png"
            )
            index += 1
            if not noted and time.time() - started > 40:
                page.fill(
                    "#noteInput",
                    "Idée clé : la sémantique n'a jamais été le web lui-même ?",
                )
                page.press("#noteInput", "Enter")
                noted = True
            if not slide_sent and capture_url and time.time() - started > 25:
                slide_path = out / "slide-demo.png"
                make_slide(browser, slide_path)
                phone = browser.new_page(
                    viewport={"width": 390, "height": 844},
                    is_mobile=True,
                    color_scheme="dark",
                )
                phone.goto(capture_url)
                phone.wait_for_timeout(800)
                phone.set_input_files("#photoInput", str(slide_path))
                phone.wait_for_timeout(1500)
                phone.close()
                slide_sent = True
        page.click("#forceBtn")
        page.wait_for_timeout(20000)
        page.screenshot(path=shots / f"{index:02d}-carte-forcee.png")
        page.click("#sourceBtn")
        page.wait_for_timeout(800)
        page.screenshot(path=shots / f"{index + 1:02d}-source.png")
        page.click("#sourceBtn")
        first_row = page.locator("#rows .cell.fr .s").nth(2)
        if first_row.count():
            first_row.click()
            page.wait_for_timeout(800)
            page.screenshot(path=shots / f"{index + 2:02d}-clic-transcription.png")
        light = browser.new_page(
            viewport={"width": 1440, "height": 900}, color_scheme="light"
        )
        light.goto(page.url)
        light.wait_for_timeout(3000)
        light.screenshot(path=shots / f"{index + 3:02d}-theme-clair.png")
        light.close()
        page.click("#qrBtn")
        page.wait_for_timeout(1000)
        page.screenshot(path=shots / f"{index + 4:02d}-qr.png")
        capture_url = page.get_attribute("#captureLink", "href") or ""
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        if capture_url:
            phone = browser.new_page(
                viewport={"width": 390, "height": 844},
                is_mobile=True,
                color_scheme="dark",
            )
            phone.goto(re.sub(r"^https?://[^/]+", BASE, capture_url))
            phone.wait_for_timeout(1500)
            phone.screenshot(path=shots / f"{index + 4:02d}-iphone.png", full_page=True)
            phone.close()
        page.click("#stopBtn")
        page.wait_for_timeout(500)
        page.screenshot(path=shots / f"{index + 5:02d}-fin-confirmation.png")
        page.click("#stopBtn")
        deadline = time.time() + 900
        step = 0
        while time.time() < deadline:
            page.wait_for_timeout(20000)
            text = (
                page.locator("#finalResult").inner_text()
                if page.locator("#finalResult").count()
                else ""
            )
            if step % 3 == 0:
                page.screenshot(
                    path=shots / f"{index + 6:02d}-finalisation-{step:02d}.png"
                )
            step += 1
            vault_written = any((JUDGE_DIR / "vault").rglob("*.canvas"))
            if vault_written or ("En cours" not in text and text.strip()):
                page.wait_for_timeout(3000)
                break
        page.screenshot(path=shots / f"{index + 7:02d}-finalisation-fin.png")
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        try:
            page.click("#finalsBtn", timeout=5000)
            page.wait_for_timeout(800)
            page.screenshot(path=shots / f"{index + 8:02d}-menu-finalisations.png")
        except Exception as error:  # noqa: BLE001 - capture facultative
            console.append(
                f"banc: menu Finalisations inaccessible ({error.__class__.__name__})"
            )
        (out / "console.log").write_text("\n".join(console), encoding="utf-8")
        browser.close()


def render_vault(out: Path) -> None:
    """Copie la note et le canvas, rend les blocs Mermaid et le canvas en PNG, la note en HTML."""
    vault_out = out / "vault"
    shutil.rmtree(vault_out, ignore_errors=True)
    if not (JUDGE_DIR / "vault").exists():
        return
    shutil.copytree(JUDGE_DIR / "vault", vault_out)
    for note in vault_out.rglob("*.md"):
        blocks = re.findall(
            r"```mermaid\n(.*?)```", note.read_text(encoding="utf-8"), flags=re.S
        )
        for number, block in enumerate(blocks, 1):
            source = out / f"mermaid-{number}.mmd"
            source.write_text(block, encoding="utf-8")
            subprocess.run(
                [
                    "mmdc",
                    "-i",
                    str(source),
                    "-o",
                    str(out / f"mermaid-{number}.png"),
                    "-t",
                    "dark",
                    "-b",
                    "#1e1e1e",
                    "-w",
                    "1600",
                ],
                capture_output=True,
            )
        import markdown

        body = markdown.markdown(
            note.read_text(encoding="utf-8"), extensions=["tables", "fenced_code"]
        )
        (out / "note-rendue.html").write_text(
            "<html><body style='background:#1e1e1e;color:#ddd;font:15px system-ui;max-width:760px;margin:auto'>"
            + body
            + "</body></html>",
            encoding="utf-8",
        )
    for canvas in vault_out.rglob("*.canvas"):
        render_canvas(canvas, out / "canvas.png")


def render_canvas(canvas_path: Path, png_path: Path) -> None:
    """Rend un .canvas Obsidian (nœuds texte, groupes, arêtes) en PNG, à la manière d'Obsidian."""
    data = json.loads(canvas_path.read_text(encoding="utf-8"))
    nodes = data.get("nodes", [])
    if not nodes:
        return
    min_x = min(node["x"] for node in nodes) - 40
    min_y = min(node["y"] for node in nodes) - 40
    width = max(node["x"] + node["width"] for node in nodes) - min_x + 40
    height = max(node["y"] + node["height"] for node in nodes) - min_y + 40
    by_id = {node["id"]: node for node in nodes}
    parts = []
    for node in sorted(nodes, key=lambda item: item.get("type") != "group"):
        left, top = node["x"] - min_x, node["y"] - min_y
        style = f"left:{left}px;top:{top}px;width:{node['width']}px;height:{node['height']}px"
        if node.get("type") == "group":
            parts.append(
                f"<div class='group' style='{style}'><span>{node.get('label', '')}</span></div>"
            )
        else:
            parts.append(
                f"<div class='card' style='{style}'>{node.get('text', node.get('file', ''))}</div>"
            )
    lines = []
    for edge in data.get("edges", []):
        source, target = by_id.get(edge["fromNode"]), by_id.get(edge["toNode"])
        if not source or not target:
            continue
        x1 = source["x"] + source["width"] / 2 - min_x
        y1 = source["y"] + source["height"] / 2 - min_y
        x2 = target["x"] + target["width"] / 2 - min_x
        y2 = target["y"] + target["height"] / 2 - min_y
        lines.append(
            f"<line x1='{x1}' y1='{y1}' x2='{x2}' y2='{y2}' stroke='#888' stroke-width='2' marker-end='url(#a)'/>"
        )
        if edge.get("label"):
            lines.append(
                f"<text x='{(x1 + x2) / 2}' y='{(y1 + y2) / 2}' fill='#bbb' font-size='13'>{edge['label']}</text>"
            )
    html = f"""<html><body style='margin:0;background:#1e1e1e'>
<style>.card{{position:absolute;box-sizing:border-box;background:#262626;border:2px solid #555;border-radius:8px;
padding:8px;color:#ddd;font:14px system-ui;overflow:hidden;white-space:pre-wrap}}
.group{{position:absolute;box-sizing:border-box;border:2px solid #666;border-radius:12px;background:rgba(255,255,255,.03)}}
.group span{{position:absolute;top:-26px;left:0;color:#ccc;font:600 16px system-ui}}</style>
<div style='position:relative;width:{width}px;height:{height}px'>{"".join(parts)}
<svg width='{width}' height='{height}' style='position:absolute;left:0;top:0'><defs><marker id='a' markerWidth='10' markerHeight='10' refX='9' refY='3' orient='auto'><path d='M0,0 L9,3 L0,6' fill='#888'/></marker></defs>{"".join(lines)}</svg>
</div></body></html>"""
    html_path = png_path.with_suffix(".html")
    html_path.write_text(html, encoding="utf-8")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": min(int(width), 4000), "height": min(int(height), 4000)}
        )
        page.goto(html_path.as_uri())
        page.screenshot(path=png_path, full_page=True)
        browser.close()


def main() -> None:
    """Point d'entrée."""
    out = Path(sys.argv[1]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    if "--render-only" in sys.argv:
        render_vault(out)
        return
    server = start_server(out / "server.log")
    try:
        if "--render-only" not in sys.argv:
            capture_ui(out)
    finally:
        server.terminate()
        server.wait(timeout=30)
    render_vault(out)
    print("captures dans", out)


if __name__ == "__main__":
    main()
