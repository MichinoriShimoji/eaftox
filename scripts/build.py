"""Build the dependency-free, offline-capable HTML. Users do not need Python."""
import base64
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
html = (ROOT / "web/index.template.html").read_text(encoding="utf-8")
html = html.replace("<!-- LICENSE -->", "<!--\n" + (ROOT / "LICENSE").read_text(encoding="utf-8").strip() + "\n-->")
for marker, filename in [("/* STYLES */", "styles.css"), ("/* CORE */", "core.js"), ("/* APPLICATION */", "app.js")]:
    content = (ROOT / "web" / filename).read_text(encoding="utf-8")
    if filename == "app.js":
        samples = [{"name": name, "type": media_type, "base64": base64.b64encode((ROOT / name).read_bytes()).decode("ascii")}
                   for name, media_type in [("sample3.eaf", "application/xml"), ("sample.wav", "audio/wav")]]
        content = content.replace("/* SAMPLE FILES */ null", json.dumps(samples, separators=(",", ":")))
    if filename.endswith(".js"):
        content = content.replace("</script", "<\\/script")
    html = html.replace(marker, content)
(ROOT / "index.html").write_text(html, encoding="utf-8")
print(f"Built index.html ({len(html.encode('utf-8')):,} bytes)")
