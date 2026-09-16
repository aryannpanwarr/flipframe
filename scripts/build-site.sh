#!/usr/bin/env bash
# Build the static site that gets deployed: landing page + the browser tool.
# The local pipeline (upload, MCP, CLI) needs a machine, so it is not part of this.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WEB="$ROOT/src/flipframe/web"
OUT="$ROOT/public"

rm -rf "$OUT"
mkdir -p "$OUT/vendor/ort"
cp "$WEB/landing.html" "$OUT/index.html"
cp "$WEB/share.html"   "$OUT/app.html"
cp "$WEB/worker.js"    "$OUT/worker.js"
cp "$WEB"/vendor/*.js  "$OUT/vendor/"
cp "$WEB"/vendor/ort/* "$OUT/vendor/ort/"
cp "$WEB/example-frame.jpg" "$OUT/example-frame.jpg"

# Links to pages that only exist on your own machine have no place on the public site.
python3 - "$OUT/index.html" <<'PY'
import re, sys
p = sys.argv[1]
html = open(p).read()
html = re.sub(r'\s*<a[^>]*href="/local"[^>]*>[^<]*</a>\s*(·)?', '', html)
open(p, 'w').write(html)
PY

echo "built $(du -sh "$OUT" | cut -f1) in $OUT"
