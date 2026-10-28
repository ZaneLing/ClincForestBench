"""Download source-authored NEJM CPC full texts from Europe PMC."""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "dataset/nejm_cpc/open_fulltexts.json"
API = "https://www.ebi.ac.uk/europepmc/webservices/rest"


def fetch(url):
    with urllib.request.urlopen(url, timeout=45) as response:
        return response.read()


class ClinicalSections(HTMLParser):
    """Collect article paragraphs by their published section heading."""

    def __init__(self):
        super().__init__()
        self.sections, self.heading, self.parts = {}, "", []
        self.capture = None

    def handle_starttag(self, tag, attrs):
        if tag == "h2":
            self.capture, self.parts = "heading", []
        elif tag == "p" and self.heading:
            self.capture, self.parts = "paragraph", []

    def handle_data(self, text):
        if self.capture:
            self.parts.append(text)

    def handle_endtag(self, tag):
        if tag == "h2" and self.capture == "heading":
            self.heading = " ".join(self.parts).strip()
            self.sections.setdefault(self.heading, [])
            self.capture = None
        elif tag == "p" and self.capture == "paragraph":
            self.sections[self.heading].append(" ".join(self.parts).strip())
            self.capture = None


def main():
    query = urllib.parse.urlencode({
        "query": "ISSN:0028-4793 AND TITLE:Case AND IN_PMC:Y",
        "format": "json", "pageSize": 100,
    })
    records = json.loads(fetch(f"{API}/search?{query}"))["resultList"]["result"]
    cases = (json.loads(DESTINATION.read_text())["cases"]
             if DESTINATION.exists() else [])
    present = {row["pmcid"] for row in cases}
    for record in records:
        if not re.match(r"Case \d+[-–]", record["title"]):
            continue
        pmcid = record["pmcid"]
        if pmcid in present:
            continue
        try:
            parser = ClinicalSections()
            parser.feed(fetch(f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/").decode())
            paragraphs = next(
                (p for heading, p in parser.sections.items()
                 if "presentation of case" in heading.lower()), [],
            )
            if not paragraphs:
                raise ValueError("missing clinical presentation section")
            text = " ".join(paragraphs)
            diagnosis = next(
                (" ".join(p).strip() for heading, p in parser.sections.items()
                 if re.search(r"^(?:anatomical|final|clinical|pathological|pathologic) diagnosis$",
                               heading, re.I)), "",
            )
            if len(text) < 450:
                raise ValueError("insufficient presentation text")
            cases.append({
                "pmid": record["id"], "pmcid": pmcid,
                "doi": record.get("doi"), "title": record["title"],
                "clinical_text": text, "reference_diagnosis": diagnosis,
                "source_url": f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/",
            })
            print(f"{len(cases)} {pmcid}", flush=True)
        except Exception as exc:
            print(f"Unavailable {pmcid}: {exc}", flush=True)
    DESTINATION.write_text(json.dumps({"cases": cases}, indent=2), encoding="utf-8")
    print(f"Saved {len(cases)} authentic open CPC presentations")


if __name__ == "__main__":
    main()
