"""Public documentation must stay linked and discoverable from its main index."""

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]


def anchors(text):
    result, seen = set(), {}
    for title in re.findall(r"^#{1,6}\s+(.+)$", text, re.MULTILINE):
        slug = re.sub(r"[^\w\s-]", "", title.lower()).strip().replace(" ", "-")
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        result.add(f"{slug}-{count}" if count else slug)
    return result


def test_public_markdown_links_and_document_index():
    graph = {}
    for document in DOCUMENTS:
        text = document.read_text(encoding="utf-8")
        links = re.findall(r"\[[^\]]*\]\(([^\s)]+)\)", text)
        destinations = set()
        for link in links:
            parsed = urlsplit(link.strip("<>"))
            if parsed.scheme or parsed.netloc:
                continue
            target = (document.parent / unquote(parsed.path)).resolve() if parsed.path else document
            assert target.exists(), f"Broken link in {document.name}: {link}"
            if target.suffix == ".md":
                if parsed.fragment:
                    assert unquote(parsed.fragment) in anchors(target.read_text(encoding="utf-8")), (
                        f"Broken heading in {document.name}: {link}"
                    )
                destinations.add(target)
        graph[document] = destinations
    reachable, remaining = set(), [ROOT / "README.md"]
    while remaining:
        document = remaining.pop()
        if document not in reachable:
            reachable.add(document)
            remaining.extend(graph.get(document, []))
    assert set(DOCUMENTS) <= reachable
    index = ROOT / "docs/README.md"
    assert set(DOCUMENTS) - {index} <= graph[index]
