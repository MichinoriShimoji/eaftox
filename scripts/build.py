"""Build the dependency-free, offline-capable HTML. Users do not need Python."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
html = (ROOT / "web/index.template.html").read_text(encoding="utf-8")
for marker, filename in [("/* STYLES */", "styles.css"), ("/* CORE */", "core.js"), ("/* APPLICATION */", "app.js")]:
    content = (ROOT / "web" / filename).read_text(encoding="utf-8")
    if filename.endswith(".js"):
        content = content.replace("</script", "<\\/script")
    html = html.replace(marker, content)
(ROOT / "index.html").write_text(html, encoding="utf-8")
print(f"Built index.html ({len(html.encode('utf-8')):,} bytes)")
