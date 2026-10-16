"""Extract EPUB body text in spine order to a plain-text file, one marker per chapter file."""
import re
import sys
import zipfile
from html import unescape

epub_path, out_path = sys.argv[1], sys.argv[2]
z = zipfile.ZipFile(epub_path)
opf = z.read("item/volume.opf").decode("utf-8")

# id -> href, then spine order
items = dict(re.findall(r'<item[^>]*id="([^"]+)"[^>]*href="([^"]+)"', opf))
items.update({i: h for h, i in re.findall(r'<item[^>]*href="([^"]+)"[^>]*id="([^"]+)"', opf)})
spine = re.findall(r'<itemref[^>]*idref="([^"]+)"', opf)

out = []
for idref in spine:
    href = items.get(idref)
    if not href or not href.endswith("xhtml"):
        continue
    html = z.read("item/" + href).decode("utf-8")
    body = re.search(r"<body.*?>(.*)</body>", html, re.S)
    body = body.group(1) if body else html
    body = re.sub(r"<rt>.*?</rt>", "", body, flags=re.S)  # drop ruby annotations
    body = re.sub(r"<(br|/p|/h\d|/div|/li)[^>]*>", "\n", body)
    text = unescape(re.sub(r"<[^>]+>", "", body))
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    out.append(f"\n\n===== [{href}] =====\n{text}")

open(out_path, "w", encoding="utf-8").write("".join(out))
total = sum(len(re.sub(r"\s", "", t)) for t in out)
print(f"chapters={len(out)} chars={total}")
