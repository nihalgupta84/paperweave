import re
from pathlib import Path

from .io import read_jsonl, write_jsonl
from .manifest import load_manifest, save_manifest, update_stage


SECTION_PATTERNS = {
    "abstract": (r"\babstract\b",),
    "introduction": (r"\bintroduction\b", r"\bbackground\b"),
    "related_work": (r"related work", r"literature review", r"prior work"),
    "methodology": (
        r"\bmethod(?:ology|s)?\b", r"proposed (?:method|approach|framework)",
        r"model architecture", r"network architecture", r"our approach",
    ),
    "datasets": (r"\bdatasets?\b", r"data collection", r"data description"),
    "experiments": (
        r"\bexperiments?\b", r"experimental setup", r"implementation details",
        r"evaluation setup", r"training details",
    ),
    "results": (r"\bresults?\b", r"quantitative", r"qualitative", r"comparison", r"ablation"),
    "discussion": (r"\bdiscussion\b", r"analysis"),
    "limitations": (r"\blimitations?\b", r"failure cases?"),
    "conclusion": (r"\bconclusions?\b", r"summary and future", r"future work"),
    "appendix": (r"\bappendix\b", r"supplementary"),
    "references": (r"\breferences\b", r"bibliography"),
}


def clean_heading(text: str) -> str:
    text = re.sub(r"^\s*(?:[IVXLC]+|\d+(?:\.\d+)*)[.)\s:-]+", "", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def classify_heading(text: str) -> str:
    heading = clean_heading(text).lower()
    for role, patterns in SECTION_PATTERNS.items():
        if any(re.search(pattern, heading) for pattern in patterns):
            return role
    return "unknown"


def assign_sections(blocks: list[dict]) -> list[dict]:
    current_heading = "Front matter"
    current_role = "unknown"
    heading_stack: list[str] = []
    output = []
    for block in blocks:
        level = block.get("heading_level")
        text = block.get("text", "").strip()
        if level and text:
            current_heading = text
            current_role = classify_heading(text)
            index = max(0, int(level) - 1)
            heading_stack = heading_stack[:index]
            heading_stack.append(text)
        elif re.match(r"^\s*abstract\b", text, re.I):
            current_heading = "Abstract"
            current_role = "abstract"
            heading_stack = [current_heading]
        enriched = dict(block)
        enriched["section_role"] = current_role
        enriched["section_path"] = list(heading_stack) if heading_stack else [current_heading]
        output.append(enriched)
    return output


def section_corpus(corpus: Path) -> dict[str, int]:
    counts = {"documents": 0, "blocks": 0}
    manifest = load_manifest(corpus)
    records_by_id = {record["document_id"]: record for record in manifest}
    for paper_dir in sorted((corpus / "papers").glob("doc_*")):
        block_path = paper_dir / "blocks.jsonl"
        if not block_path.exists():
            continue
        blocks = assign_sections(read_jsonl(block_path))
        write_jsonl(paper_dir / "sections.jsonl", blocks)
        counts["documents"] += 1
        counts["blocks"] += len(blocks)
        if paper_dir.name in records_by_id:
            update_stage(records_by_id[paper_dir.name], "sectioning", "complete")
    if manifest:
        save_manifest(corpus, manifest)
    return counts
