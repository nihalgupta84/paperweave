"""Corpus-local citation, related-paper, and entity graph construction."""

from __future__ import annotations

import logging
import math
import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from .ingestion import title_key
from .io import read_json, write_json
from .merge import strong_identity_match

logger = logging.getLogger(__name__)
WORD = re.compile(r"[A-Za-z][A-Za-z0-9_+-]{2,}")
STOP = {"the", "and", "for", "with", "from", "that", "this", "using", "method", "paper", "based"}


def _reference_key(reference: dict[str, Any]) -> str:
    if reference.get("doi"):
        return f"doi:{reference['doi'].casefold()}"
    if reference.get("arxiv_id"):
        return f"arxiv:{reference['arxiv_id'].casefold()}"
    return f"title:{title_key(reference.get('parsed_title') or reference.get('raw', ''))}"


def _references(record_dir: Path) -> list[dict[str, Any]]:
    deterministic = read_json(record_dir / "references.json", {}).get("references", [])
    grobid = read_json(record_dir / "grobid_references.json", {}).get("references", [])
    seen: set[str] = set()
    values = []
    for reference in [*deterministic, *grobid]:
        key = _reference_key(reference)
        if key not in seen and not key.endswith("title:"):
            values.append(reference)
            seen.add(key)
    return values


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _cosine(left: Counter[str], right: Counter[str]) -> float:
    denominator = math.sqrt(
        sum(value * value for value in left.values()) * sum(value * value for value in right.values())
    )
    return sum(value * right.get(key, 0) for key, value in left.items()) / denominator if denominator else 0.0


def _work_features(record_dir: Path, work: dict[str, Any]) -> dict[str, Any]:
    taxonomy = read_json(record_dir / "taxonomy.json", {}).get("facets", {})
    facets = {
        assignment.get("id", "")
        for assignments in taxonomy.values()
        for assignment in assignments
        if assignment.get("id")
    }
    experiments = read_json(record_dir / "experiments.json", {})
    datasets = {
        str(item.get("name") or item.get("id") or item.get("value", "")).casefold()
        for item in experiments.get("datasets", [])
        if item.get("name") or item.get("id") or item.get("value")
    }
    analysis = read_json(record_dir / "analysis.json", {})
    method_text = " ".join(item.get("statement", "") for item in analysis.get("methodology", []))
    words = Counter(
        token.casefold()
        for token in WORD.findall(f"{work.get('title', '')} {method_text}")
        if token.casefold() not in STOP
    )
    references = _references(record_dir)
    return {
        "facets": facets,
        "datasets": datasets,
        "words": words,
        "reference_keys": {_reference_key(reference) for reference in references},
        "references": references,
    }


def _graphml(path: Path, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> None:
    graphml = ElementTree.Element("graphml", xmlns="http://graphml.graphdrawing.org/xmlns")
    ElementTree.SubElement(graphml, "key", id="label", **{"for": "node", "attr.name": "label", "attr.type": "string"})
    ElementTree.SubElement(graphml, "key", id="type", **{"for": "all", "attr.name": "type", "attr.type": "string"})
    ElementTree.SubElement(graphml, "key", id="weight", **{"for": "edge", "attr.name": "weight", "attr.type": "double"})
    graph = ElementTree.SubElement(graphml, "graph", edgedefault="directed")
    for node in nodes:
        element = ElementTree.SubElement(graph, "node", id=node["id"])
        ElementTree.SubElement(element, "data", key="label").text = str(node.get("label", node["id"]))
        ElementTree.SubElement(element, "data", key="type").text = str(node.get("type", "unknown"))
    for index, edge in enumerate(edges):
        attributes = {"id": f"e{index}", "source": edge["source"], "target": edge["target"]}
        if edge.get("type") == "related":
            attributes["directed"] = "false"
        element = ElementTree.SubElement(graph, "edge", **attributes)
        ElementTree.SubElement(element, "data", key="type").text = str(edge.get("type", "related"))
        ElementTree.SubElement(element, "data", key="weight").text = str(edge.get("weight", 1.0))
    path.parent.mkdir(parents=True, exist_ok=True)
    ElementTree.ElementTree(graphml).write(path, encoding="utf-8", xml_declaration=True)


def build_citation_graph(
    corpus: Path, similarity_threshold: float = 0.85, related_threshold: float = 0.16, related_per_paper: int = 5
) -> dict[str, Any]:
    """Build directed citations and explainable, corpus-local related-paper links."""
    (corpus / "records").mkdir(parents=True, exist_ok=True)
    (corpus / "synthesis").mkdir(parents=True, exist_ok=True)
    works: dict[str, dict[str, Any]] = {}
    features: dict[str, dict[str, Any]] = {}
    record_dirs: dict[str, Path] = {}
    for record_dir in sorted((corpus / "records").glob("work_*")):
        work = read_json(record_dir / "work.json", {})
        if not work:
            continue
        work_id = work["work_id"]
        works[work_id] = {
            "work_id": work_id,
            "title": work.get("title", ""),
            "title_key": title_key(work.get("title", "")),
            "year": work.get("year"),
            "authors": work.get("authors", []),
            "doi": work.get("doi"),
            "arxiv_id": work.get("arxiv_id"),
        }
        record_dirs[work_id] = record_dir
        features[work_id] = _work_features(record_dir, work)

    citation_edges: list[dict[str, Any]] = []
    in_citations: Counter[str] = Counter()
    for source_work_id, source_work in works.items():
        for reference in features[source_work_id]["references"]:
            raw = reference.get("raw", "")
            parsed_title = reference.get("parsed_title") or raw
            ref_key = title_key(parsed_title)
            if len(ref_key) < 8 and not (reference.get("doi") or reference.get("arxiv_id")):
                continue
            best_match = None
            for target_work_id, target_work in works.items():
                if target_work_id == source_work_id:
                    continue
                identity_match, identity_reason = strong_identity_match(reference, target_work)
                similarity = SequenceMatcher(None, ref_key, target_work["title_key"]).ratio()
                contains_title = len(target_work["title_key"]) >= 12 and target_work["title_key"] in title_key(raw)
                if identity_match:
                    candidate = (2.0, target_work_id, 1.0, "verified", identity_reason)
                elif similarity >= similarity_threshold or contains_title:
                    candidate = (similarity, target_work_id, similarity, "candidate", "fuzzy_title")
                else:
                    continue
                if best_match is None or candidate[0] > best_match[0]:
                    best_match = candidate
            if best_match:
                _, target_work_id, confidence, status, method = best_match
                citation_edges.append(
                    {
                        "source_work_id": source_work_id,
                        "source_title": source_work["title"],
                        "target_work_id": target_work_id,
                        "target_title": works[target_work_id]["title"],
                        "edge_type": "citation",
                        "confidence": round(confidence, 4),
                        "status": status,
                        "match_method": method,
                        "reference_raw": raw[:200],
                    }
                )
                if status == "verified":
                    in_citations[target_work_id] += 1

    related_candidates: dict[str, list[tuple[float, str, dict[str, float]]]] = defaultdict(list)
    work_ids = sorted(works)
    for index, left_id in enumerate(work_ids):
        for right_id in work_ids[index + 1 :]:
            left, right = features[left_id], features[right_id]
            components = {
                "taxonomy": _jaccard(left["facets"], right["facets"]),
                "datasets": _jaccard(left["datasets"], right["datasets"]),
                "method_text": _cosine(left["words"], right["words"]),
                "bibliographic_coupling": _jaccard(left["reference_keys"], right["reference_keys"]),
            }
            score = (
                0.25 * components["taxonomy"]
                + 0.20 * components["datasets"]
                + 0.35 * components["method_text"]
                + 0.20 * components["bibliographic_coupling"]
            )
            active_signals = sum(value > 0 for value in components.values())
            if score >= related_threshold and (
                active_signals >= 2 or components["method_text"] >= 0.55 or components["bibliographic_coupling"] >= 0.2
            ):
                related_candidates[left_id].append((score, right_id, components))
                related_candidates[right_id].append((score, left_id, components))

    selected_pairs: dict[tuple[str, str], tuple[float, dict[str, float]]] = {}
    for source_id, candidates in related_candidates.items():
        for score, target_id, components in sorted(candidates, reverse=True)[:related_per_paper]:
            pair = tuple(sorted((source_id, target_id)))
            if pair not in selected_pairs or score > selected_pairs[pair][0]:
                selected_pairs[pair] = (score, components)
    related_edges = [
        {
            "source_work_id": left,
            "source_title": works[left]["title"],
            "target_work_id": right,
            "target_title": works[right]["title"],
            "edge_type": "related",
            "status": "computed",
            "score": round(score, 4),
            "components": {key: round(value, 4) for key, value in components.items()},
        }
        for (left, right), (score, components) in sorted(selected_pairs.items())
    ]

    graph_data = {
        "nodes": list(works.values()),
        "edges": [*citation_edges, *related_edges],
        "summary": {
            "total_works": len(works),
            "internal_citations": len(citation_edges),
            "verified_identifier_links": sum(edge["status"] == "verified" for edge in citation_edges),
            "title_match_candidates": sum(edge["status"] == "candidate" for edge in citation_edges),
            "related_paper_links": len(related_edges),
        },
    }
    write_json(corpus / "records" / "citation_graph.json", graph_data)

    lines = [
        "# Corpus Paper Graph",
        "",
        "This report shows how papers already present in this corpus are connected.",
        "",
        "- **Citation link:** one paper's bibliography appears to reference another corpus paper.",
        "- **Related link:** papers share method language, datasets, taxonomy labels, or references. This is not a citation.",
        "- **Verified:** matched by DOI or arXiv ID. **Candidate:** title-based match requiring review.",
        "",
        "PaperWeave does not search the global literature network like Connected Papers or Litmaps.",
        "",
        "## Summary",
        "",
        f"- Works: {len(works)}",
        f"- Citation links: {len(citation_edges)}",
        f"- Identifier-verified citations: {graph_data['summary']['verified_identifier_links']}",
        f"- Fuzzy citation candidates requiring review: {graph_data['summary']['title_match_candidates']}",
        f"- Related-paper links: {len(related_edges)}",
        "",
        "## Most Cited Works",
        "",
    ]
    cited = [(count, work_id) for work_id, count in in_citations.items() if count]
    lines.extend(
        f"- **{works[work_id]['title']}** (`{work_id}`): {count} verified in-corpus citation(s)"
        for count, work_id in sorted(cited, reverse=True)
    )
    if not cited:
        lines.append("No identifier-verified in-corpus citations were detected.")
    lines.extend(["", "## Related Papers", ""])
    for edge in sorted(related_edges, key=lambda item: item["score"], reverse=True):
        components = ", ".join(f"{key}={value}" for key, value in edge["components"].items() if value)
        lines.append(f"- **{edge['source_title']}** ↔ **{edge['target_title']}** — {edge['score']} ({components})")
    if not related_edges:
        lines.append("No related-paper links exceeded the configured threshold.")
    lines.append("")
    (corpus / "synthesis" / "citation_graph.md").write_text("\n".join(lines), encoding="utf-8")

    graph_nodes = [{"id": item["work_id"], "label": item["title"], "type": "paper"} for item in works.values()]
    graph_edges = [
        {
            "source": edge["source_work_id"],
            "target": edge["target_work_id"],
            "type": edge["edge_type"],
            "weight": edge.get("score", edge.get("confidence", 1.0)),
        }
        for edge in graph_data["edges"]
    ]
    _graphml(corpus / "records" / "paper_graph.graphml", graph_nodes, graph_edges)
    logger.info("Built paper graph with %d nodes and %d edges", len(works), len(graph_data["edges"]))
    return {"nodes": len(works), "edges": len(graph_data["edges"]), **graph_data["summary"]}


def build_knowledge_graph(corpus: Path) -> dict[str, Any]:
    """Build a heterogeneous graph of papers, datasets, taxonomy labels, and citations."""
    paper_result = build_citation_graph(corpus)
    paper_graph = read_json(corpus / "records" / "citation_graph.json", {})
    nodes: dict[str, dict[str, Any]] = {
        item["work_id"]: {"id": item["work_id"], "label": item["title"], "type": "paper", **item}
        for item in paper_graph.get("nodes", [])
    }
    edges: list[dict[str, Any]] = []
    for edge in paper_graph.get("edges", []):
        edges.append(
            {
                "source": edge["source_work_id"],
                "target": edge["target_work_id"],
                "type": edge["edge_type"],
                "status": edge.get("status"),
                "weight": edge.get("score", edge.get("confidence", 1.0)),
            }
        )

    for record_dir in sorted((corpus / "records").glob("work_*")):
        work = read_json(record_dir / "work.json", {})
        if not work:
            continue
        work_id = work["work_id"]
        experiments = read_json(record_dir / "experiments.json", {})
        for dataset in experiments.get("datasets", []):
            label = str(dataset.get("name") or dataset.get("id") or dataset.get("value", "")).strip()
            if not label:
                continue
            node_id = f"dataset:{title_key(label)}"
            nodes.setdefault(node_id, {"id": node_id, "label": label, "type": "dataset"})
            edges.append({"source": work_id, "target": node_id, "type": "evaluated_on", "weight": 1.0})
        facets = read_json(record_dir / "taxonomy.json", {}).get("facets", {})
        for facet_name, assignments in facets.items():
            for assignment in assignments:
                label_id = assignment.get("id")
                if not label_id:
                    continue
                node_id = f"facet:{label_id}"
                nodes.setdefault(
                    node_id,
                    {"id": node_id, "label": assignment.get("name", label_id), "type": "taxonomy", "facet": facet_name},
                )
                edges.append({"source": work_id, "target": node_id, "type": "classified_as", "weight": 1.0})

    unique_edges: dict[tuple[str, str, str], dict[str, Any]] = {}
    for edge in edges:
        unique_edges[(edge["source"], edge["target"], edge["type"])] = edge
    edges = list(unique_edges.values())
    payload = {
        "nodes": list(nodes.values()),
        "edges": edges,
        "summary": {
            "nodes": len(nodes),
            "edges": len(edges),
            "paper_nodes": paper_result["nodes"],
            "paper_edges": paper_result["edges"],
            "internal_citations": paper_result["internal_citations"],
            "verified_identifier_links": paper_result["verified_identifier_links"],
            "title_match_candidates": paper_result["title_match_candidates"],
            "related_paper_links": paper_result["related_paper_links"],
        },
    }
    write_json(corpus / "records" / "knowledge_graph.json", payload)
    _graphml(corpus / "records" / "knowledge_graph.graphml", payload["nodes"], edges)
    return payload["summary"]
