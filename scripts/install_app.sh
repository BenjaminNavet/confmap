#!/bin/bash
# Installe ~/Applications/confmap.app : lançable depuis Spotlight en tapant « confmap ».
# L'app démarre le serveur s'il ne tourne pas, puis ouvre http://localhost:8010.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP="$HOME/Applications/confmap.app"
PORT="${CONFMAP_PORT:-8010}"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>confmap</string>
  <key>CFBundleDisplayName</key><string>confmap</string>
  <key>CFBundleIdentifier</key><string>fr.navet.confmap</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>confmap</string>
  <key>CFBundleIconFile</key><string>confmap</string>
  <key>LSUIElement</key><true/>
  <key>NSMicrophoneUsageDescription</key><string>confmap enregistre la conférence pour la transcrire.</string>
</dict>
</plist>
PLIST

cat > "$APP/Contents/MacOS/confmap" <<LAUNCHER
#!/bin/bash
export PATH="\$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
URL="http://localhost:$PORT"
LOG="\$HOME/Library/Logs/confmap.log"
if ! curl -s -o /dev/null "\$URL/"; then
  cd "$PROJECT_DIR"
  nohup uv run confmap serve --port $PORT >> "\$LOG" 2>&1 &
  for _ in \$(seq 1 120); do
    curl -s -o /dev/null "\$URL/" && break
    sleep 0.5
  done
fi
[ -n "\${CONFMAP_NO_OPEN:-}" ] || open "\$URL"
LAUNCHER
chmod +x "$APP/Contents/MacOS/confmap"

# Icône générée (carte d'idées stylisée).
ICONSET="$(mktemp -d)/confmap.iconset"
mkdir -p "$ICONSET"
(cd "$PROJECT_DIR" && uv run --quiet python - "$ICONSET" <<'PY'
import sys
from PIL import Image, ImageDraw

out = sys.argv[1]
size = 1024
img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)
draw.rounded_rectangle((60, 60, 964, 964), radius=200, fill=(25, 28, 32))
nodes = [(512, 300), (300, 560), (724, 560), (220, 790), (400, 790), (724, 790)]
for a, b in [(0, 1), (0, 2), (1, 3), (1, 4), (2, 5)]:
    draw.line([nodes[a], nodes[b]], fill=(100, 106, 115), width=22)
colors = [(76, 141, 255), (52, 211, 153), (244, 114, 182), (52, 211, 153), (52, 211, 153), (244, 114, 182)]
for (x, y), color in zip(nodes, colors):
    draw.rounded_rectangle((x - 80, y - 46, x + 80, y + 46), radius=26, fill=(32, 36, 42), outline=color, width=16)
for px in (16, 32, 128, 256, 512):
    img.resize((px, px), Image.LANCZOS).save(f"{out}/icon_{px}x{px}.png")
    img.resize((px * 2, px * 2), Image.LANCZOS).save(f"{out}/icon_{px}x{px}@2x.png")
PY
)
iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/confmap.icns"

codesign --force -s - "$APP" >/dev/null 2>&1 || true
touch "$APP"
mdimport "$APP" 2>/dev/null || true
echo "Installé : $APP (Spotlight → « confmap »)"
