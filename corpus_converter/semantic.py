"""Deterministic and LLM-assisted semantic analysis and evidence extraction."""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from .io import read_json, read_jsonl, write_json
from .manifest import load_manifest, save_manifest, update_stage
from .references import extract_and_save_references
from .validation import validate_analysis, validate_experiments, validate_work

logger = logging.getLogger(__name__)

DEFAULT_ENTITIES_FILE = Path(__file__).resolve().parent / "taxonomies" / "entities.json"
ENTITY_ROLES = {"abstract", "methodology", "experiments", "datasets", "results", "discussion", "conclusion"}
DATASET_STOPWORDS = {
    "a",
    "about",
    "above",
    "across",
    "after",
    "against",
    "all",
    "along",
    "among",
    "an",
    "and",
    "another",
    "any",
    "around",
    "as",
    "at",
    "before",
    "behind",
    "below",
    "benchmark",
    "beneath",
    "beside",
    "between",
    "beyond",
    "both",
    "but",
    "by",
    "clinical",
    "cohort",
    "cohorts",
    "concerning",
    "data",
    "dataset",
    "datasets",
    "despite",
    "different",
    "down",
    "during",
    "each",
    "either",
    "every",
    "except",
    "external",
    "following",
    "for",
    "from",
    "in",
    "inside",
    "internal",
    "into",
    "its",
    "like",
    "near",
    "neither",
    "new",
    "next",
    "no",
    "nor",
    "not",
    "of",
    "off",
    "on",
    "onto",
    "or",
    "other",
    "our",
    "out",
    "outside",
    "over",
    "past",
    "per",
    "private",
    "public",
    "regarding",
    "round",
    "segmentation",
    "setting",
    "settings",
    "several",
    "since",
    "so",
    "some",
    "source",
    "such",
    "test",
    "testing",
    "than",
    "that",
    "the",
    "their",
    "them",
    "these",
    "this",
    "those",
    "through",
    "throughout",
    "till",
    "to",
    "toward",
    "towards",
    "training",
    "under",
    "underneath",
    "unlike",
    "until",
    "up",
    "upon",
    "using",
    "validation",
    "via",
    "with",
    "within",
    "without",
}

# Full phrases or single words that, after stopword stripping, are never
# legitimate standalone dataset names. Checked via casefold().
DATASET_FALSE_POSITIVES = {
    # Demonstratives / conjunctions / adverbs
    "although",
    "because",
    "besides",
    "consequently",
    "furthermore",
    "however",
    "moreover",
    "nevertheless",
    "nonetheless",
    "notably",
    "notable",
    "particularly",
    "respectively",
    "similarly",
    "specifically",
    "such",
    "that",
    "therefore",
    "these",
    "this",
    "those",
    "thus",
    "additionally",
    "alternatively",
    "conversely",
    "including",
    "meanwhile",
    "otherwise",
    "subsequently",
    "whereas",
    # Imaging modalities — never a dataset by themselves
    "rgb",
    "rgb-d",
    "rgbd",
    "rgb-polarization",
    "polarization",
    "polarized",
    "depth",
    "lidar",
    "radar",
    "monocular",
    "stereo",
    "multiview",
    "multi-view",
    "light field",
    "lightfield",
    "lf",
    "point cloud",
    "pointcloud",
    "mesh",
    "surface normal",
    "disparity",
    "optical flow",
    "flow",
    "event",
    "event-based",
    "thermal",
    "infrared",
    "tof",
    "itof",
    "dtof",
    "ct",
    "mri",
    "pet",
    "spect",
    "xray",
    "x-ray",
    "ultrasound",
    "histology",
    "endoscopy",
    "fluoroscopy",
    "mammography",
    "oct",
    "dermoscopy",
    "fundoscopy",
    "ecg",
    "eeg",
    "reflection",
    "refraction",
    "transmission",
    # Anatomy / clinical terms that appear near "dataset" but are not names
    "abdominal",
    "cardiac",
    "cerebral",
    "cervical",
    "colorectal",
    "hepatic",
    "lung",
    "pancreatic",
    "prostate",
    "rectal",
    "renal",
    "retinal",
    "thoracic",
    # Generic qualifiers / adjectives
    "clinical",
    "large scale",
    "large-scale",
    "medical",
    "multicenter",
    "multicentre",
    "prospective",
    "retrospective",
    "single-center",
    "single-centre",
    "synthetic",
    "real",
    "real-world",
    "simulated",
    "photorealistic",
    "rendered",
    "indoor",
    "outdoor",
    "transparent",
    "specular",
    "mirror",
    "glass",
    "reflective",
    "refractive",
    "generic",
    "specialized",
    "custom",
    "proprietary",
    "public",
    "private",
    "internal",
    "external",
    "novel",
    "proposed",
    "our",
    "new",
    "existing",
    "prior",
    "baseline",
    "benchmark",
    "evaluation",
    "test",
    "testing",
    "train",
    "training",
    "val",
    "validation",
    "pretraining",
    "pre-training",
    "fine-tuning",
    "ablation",
    "perspective",
    "panoramic",
    "fisheye",
    "spherical",
    "early",
    "recent",
    "later",
    "other",
    "another",
    "all",
    "both",
    "each",
    "every",
    "individual",
    "several",
    "various",
    "different",
    "multiple",
    "single",
    "few",
    "many",
    "whole",
    "full",
    "raw",
    "processed",
    "clean",
    "noisy",
    "labeled",
    "unlabeled",
    "annotated",
    "ground-truth",
    "groundtruth",
    "supervision",
    # Document / Noun structural terms
    "datum",
    "corpus",
    "database",
    "scene",
    "scenes",
    "image",
    "images",
    "frame",
    "frames",
    "sample",
    "samples",
    "object",
    "objects",
    "surface",
    "surfaces",
    "target",
    "targets",
    "source",
    "sources",
    "domain",
    "domains",
    "environment",
    "environments",
    "detail",
    "details",
    "statistic",
    "statistics",
    "table",
    "figure",
    "fig",
    "section",
    "appendix",
    "experiment",
    "experiments",
    "result",
    "results",
    "comparison",
    "comparisons",
    "method",
    "methods",
    "model",
    "models",
    "approach",
    "approaches",
    "algorithm",
    "algorithms",
    "framework",
    "pipeline",
    "architecture",
    "module",
    "design",
    "performance",
    "accuracy",
    "error",
    "metric",
    "metrics",
    "setup",
    "protocol",
    "setting",
    "settings",
    "task",
    "tasks",
    "challenge",
    "dl-test",
    "dl-test-real",
    "apple",
    "maria",
    "tiger",
    "walls",
    "toronto",
    "affordance",
    "detection",
    "segmentation",
}

CANONICAL_DATASET_MAP: dict[str, str] = {
    "nyu depth v2": "NYUv2",
    "nyu-v2": "NYUv2",
    "nyuv2": "NYUv2",
    "nyuv2-raw": "NYUv2",
    "nyuv2-ref": "NYUv2",
    "cleargrasp": "ClearGrasp",
    "cleargrasp real": "ClearGrasp",
    "clear-grasp real-novel": "ClearGrasp",
    "clearpose": "ClearPose",
    "cleardepth": "ClearDepth",
    "transcg": "TransCG",
    "trans10k": "Trans10K",
    "trans10 k": "Trans10K",
    "transcene": "TranScene",
    "scannet": "ScanNet",
    "scannet-reflection": "ScanNet",
    "scannet-noreflection": "ScanNet",
    "matterport3d": "Matterport3D",
    "mp3d-mesh": "Matterport3D",
    "mp3d-mesh-ref": "Matterport3D",
    "mp3dmesh-ref": "Matterport3D",
    "todd": "TODD",
    "tod": "TODD",
    "syn-todd": "TODD",
    "toronto transparent objects depth": "TODD",
    "gw-depth": "GW-Depth",
    "gw depth": "GW-Depth",
    "glass walls depth": "GW-Depth",
    "glass-depth eval": "GW-Depth",
    "ptod": "PTOD",
    "polarized transparent object": "PTOD",
    "xyz-ibd": "XYZ-IBD",
    "xyz industrial bin picking": "XYZ-IBD",
    "gift-i": "GIFT",
    "gift-intervention": "GIFT",
    "gift": "GIFT",
    "omniverse": "Omniverse Object",
    "omniverse object": "Omniverse Object",
    "scene flow": "Scene Flow",
    "booster": "Booster",
    "laion": "LAION",
    "coco": "COCO",
    "kitti": "KITTI",
    "imagenet": "ImageNet",
    "sintel": "Sintel",
    "mpi-sintel": "Sintel",
    "crestereo": "CREStereo",
    "flyingthings3d": "FlyingThings3D",
    "afordpose": "AfordPose",
    "gdd": "GDD",
    "msd": "MSD",
    "mirror3d": "Mirror3D",
    "hammer": "HAMMER",
    "hcinew": "HCInew",
    "layereddepth-syn": "LayeredDepth-Syn",
    "tartanair": "TartanAir",
    "mvtrans": "MVTrans",
}


def canonicalize_dataset_name(name: str) -> str:
    """Normalize dataset name variations, sub-splits, and casing to canonical benchmark names."""
    trimmed = name.strip()
    key = trimmed.casefold()
    if key in CANONICAL_DATASET_MAP:
        return CANONICAL_DATASET_MAP[key]
    return trimmed


def load_entities(custom_path: str | Path | None = None) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Load target datasets and metrics tuples from a JSON configuration."""
    target = Path(custom_path).expanduser().resolve() if custom_path else DEFAULT_ENTITIES_FILE
    data = read_json(target, {})
    datasets = tuple(data.get("datasets", []))
    metrics = tuple(data.get("metrics", []))
    if not datasets or not metrics:
        # Fallback to defaults if file missing or corrupt
        datasets = (
            "ImageNet",
            "COCO",
            "CIFAR-10",
            "CIFAR-100",
            "MNIST",
            "Cityscapes",
            "Twitter",
            "Reddit",
            "eRisk",
            "CLPsych",
            "DAIC-WOZ",
            "Sintel",
            "KITTI",
        )
        metrics = (
            "accuracy",
            "precision",
            "recall",
            "F1",
            "F1-score",
            "AUC",
            "AUROC",
            "mAP",
            "IoU",
            "Dice",
            "EPE",
            "endpoint error",
            "Fl-all",
            "FPS",
            "latency",
            "parameters",
            "FLOPs",
        )
    return datasets, metrics


def evidence(block: dict[str, Any]) -> dict[str, Any]:
    """Generate an evidence locator dict for a given block."""
    return {
        "document_id": block["document_id"],
        "block_id": block["block_id"],
        "page_index": block.get("page_index"),
        "section": " > ".join(block.get("section_path") or []),
    }


def statement(block: dict[str, Any], text: str | None = None) -> dict[str, Any]:
    """Generate a supported statement citing the provided block."""
    return {
        "statement": text or block.get("text", "").strip(),
        "support_status": "supported",
        "evidence": [evidence(block)],
    }


def substantive(block: dict[str, Any]) -> bool:
    """Check if a block contains substantive text."""
    text = block.get("text", "").strip()
    return block.get("type") not in {"header", "footer", "page_footnote"} and len(text) >= 80


def select(blocks: list[dict[str, Any]], roles: set[str], limit: int) -> list[dict[str, Any]]:
    """Select substantive blocks matching specific section roles."""
    selected = [block for block in blocks if block.get("section_role") in roles and substantive(block)]
    return selected[:limit]


def term_present(text: str, term: str) -> bool:
    """Match an entity as a complete token sequence instead of a substring."""
    return bool(re.search(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", text, re.I))


def relevant_entity_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return body blocks likely to contain experimental entities."""
    return [
        block
        for block in blocks
        if block.get("section_role") in ENTITY_ROLES
        and block.get("type") not in {"header", "footer", "page_number", "page_footnote", "heading"}
        and block.get("heading_level") is None
        and block.get("text", "").strip()
    ]


def find_mentions(blocks: list[dict[str, Any]], terms: tuple[str, ...]) -> list[dict[str, Any]]:
    """Find entity mentions with source block citations."""
    found = {}
    for block in blocks:
        text = block.get("text", "")
        for term in terms:
            canonical = canonicalize_dataset_name(term)
            if canonical.casefold() not in found and term_present(text, term):
                found[canonical.casefold()] = {"name": canonical, "evidence": [evidence(block)]}
    return list(found.values())


def _clean_dataset_candidate(value: str) -> str | None:
    # Strip citation references and numeric parentheticals
    value = re.sub(r"\[[^]]+\]|\([^)]*\d[^)]*\)", " ", value)
    # Normalize spaced acronyms & letter-digit spaces (e.g. "W O R D" -> "WORD", "TRANS10 K" -> "TRANS10K")
    value = re.sub(r"\b([A-Za-z]+)\s+(\d+)\s+([A-Za-z]+)\b", r"\1\2\3", value)
    value = re.sub(r"\b([A-Za-z0-9]+)\s+([0-9]+)\s+([A-Za-z]+)\b", r"\1\2\3", value)
    value = re.sub(r"\b([A-Z])\s+([A-Z])\s+([A-Z])\s+([A-Z])\b", r"\1\2\3\4", value)
    value = re.sub(r"\b([A-Z])\s+([A-Z])\s+([A-Z])\b", r"\1\2\3", value)
    value = re.sub(r"\s+", " ", value).strip(" ,.;:–—-")

    # Reject candidates containing sentence-ending punctuation inside them
    if re.search(r"[.!?]\s+[A-Z]", value):
        return None

    # Reject multi-word candidates starting with section-title prefixes
    # (catches "Construction of CARE", "Description of WORD", "Overview of ...")
    if re.match(
        r"^(?:construction|description|overview|analysis|evaluation|"
        r"comparison|application|introduction|utilization|collection|"
        r"preparation|annotation|curation|summary|details)\s+of\b",
        value,
        re.I,
    ):
        return None

    # If the candidate contains prepositions like "on the", "for the", "using the", take what follows
    prep_match = list(
        re.finditer(
            r"\b(?:on|for|in|using|with|across|from|over|into|onto)\s+(?:the\s+|our\s+|a\s+|an\s+)?",
            value,
            re.I,
        )
    )
    if prep_match:
        value = value[prep_match[-1].end() :].strip()

    # Multi-pass stripping of leading prefixes (table titles, verbs, section markers, etc.)
    lead_pattern = re.compile(
        r"^(?:(?:[ivxlcdm]+|\d+|[a-z\d]+)\.\s+|unlike\b|following\b|regarding\b|concerning\b|during\b|according\s+to\b|does\b|is\b|are\b|were\b|was\b|can\b|could\b|will\b|would\b|what\b|who\b|which\b|where\b|when\b|why\b|how\b|since\b|as\b|because\b|if\b|when\b|while\b|whereas\b|although\b|though\b|however\b|(?:construction|curation|collection|annotation|generation|acquisition|preparation|statistics|description|details|overview|evaluation|comparison|analysis|setup|protocol|results|experiments|baseline|fusion\s+design)\s+of\s+(?:the\s+)?|results\s+on\b|evaluation\s+on\b|experiments\s+on\b|baseline\s+on\b|fusion\s+design\s+on\b|table\s+[ivxlcdm\d]+\b|fig(?:ure)?\.?\s*\d+\b|section\s+[a-z\d]+\b|appendix\s+[a-z\d]+\b)\s*",
        re.I,
    )
    for _ in range(3):
        value = value.strip(" ,.;:–—-")
        value = lead_pattern.sub("", value).strip()
        value = re.sub(r"^(?:the|our|a|an)\s+", "", value, flags=re.I).strip()

    words = value.split()
    while words and words[0].casefold() in DATASET_STOPWORDS:
        words.pop(0)
    while words and words[-1].casefold() in DATASET_STOPWORDS:
        words.pop()

    # Strip leading single section letters like "D " in "D Glass ..."
    if len(words) >= 2 and len(words[0]) == 1 and words[0].isalpha():
        words.pop(0)

    value = " ".join(words)

    # Reject empty, too long, too many words
    if not value or len(value) > 60 or len(words) > 4:
        return None

    # Reject task descriptors (tasks are never dataset names)
    if value.casefold().endswith(
        (
            " detection",
            " segmentation",
            " estimation",
            " classification",
            " reconstruction",
            " completion",
            " recognition",
            " tracking",
            " matching",
        )
    ):
        return None

    # Reject single letters, short abbreviations without digits, section numbering (e.g. C.1, A2b, I, D)
    if len(value) <= 2 and not re.search(r"\d", value):
        return None
    if (
        re.match(r"^[A-Z]\.?$", value)
        or re.match(r"^[ivxlcdm]+\.?$", value, re.I)
        or re.match(r"^[a-z]?\d+[a-z]?\.?$", value, re.I)
        or re.match(r"^[A-Z]\.\d+\b", value)
        or re.match(r"^Q\d+\b", value, re.I)
    ):
        return None

    if value.casefold() in DATASET_STOPWORDS or not re.search(r"[A-Z0-9]", value):
        return None

    # Reject if matches false positives
    if value.casefold() in DATASET_FALSE_POSITIVES:
        return None

    # Reject if all constituent words are generic/stopwords
    if all(w.casefold() in DATASET_STOPWORDS or w.casefold() in DATASET_FALSE_POSITIVES for w in words):
        return None

    # Canonicalize
    return canonicalize_dataset_name(value)


def discover_dataset_mentions(blocks: list[dict[str, Any]], configured: tuple[str, ...]) -> list[dict[str, Any]]:
    """Discover named datasets from evidence text as well as a configured vocabulary."""
    relevant = relevant_entity_blocks(blocks)
    found = {item["name"].casefold(): item for item in find_mentions(relevant, configured)}
    single = re.compile(r"\b((?:[A-Z][A-Za-z0-9+_.-]*)(?:\s+(?:[A-Z][A-Za-z0-9+_.-]*|of|the)){0,5})\s+(?i:datasets?)\b")
    coordinated = re.compile(r"\b([A-Z][A-Za-z0-9+_.-]*(?:\s*(?:,|and)\s*[A-Z][A-Za-z0-9+_.-]*)+)\s+(?i:datasets?)\b")
    named = re.compile(r"\bdatasets?\s*(?:is|was|are|were)?\s*(?:called|named)\s+([A-Z][A-Za-z0-9+_.-]*)", re.I)
    examples = re.compile(
        r"\bdatasets?\s+(?:such as|including|like)\s+([A-Z][A-Za-z0-9+_.-]*(?:\s*(?:,|and)\s*[A-Z][A-Za-z0-9+_.-]*)*)",
        re.I,
    )

    for block in relevant:
        text = re.sub(r"<sup\b[^>]*>.*?</sup>", "", block.get("text", ""), flags=re.I | re.S)
        text = re.sub(r"<[^>]+>", "", text)
        candidates = []
        for match in single.finditer(text):
            candidates.extend(re.split(r"\s*(?:,|&|\band\b)\s*", match.group(1), flags=re.I))
        for match in named.finditer(text):
            candidates.extend(re.split(r"\s*(?:,|&|\band\b)\s*", match.group(1), flags=re.I))
        for match in examples.finditer(text):
            candidates.extend(re.split(r"\s*(?:,|&|\band\b)\s*", match.group(1), flags=re.I))
        for match in coordinated.finditer(text):
            candidates.extend(re.split(r"\s*(?:,|&|\band\b)\s*", match.group(1), flags=re.I))
        for candidate in candidates:
            cleaned = _clean_dataset_candidate(candidate)
            if cleaned and cleaned.casefold() not in found:
                found[cleaned.casefold()] = {
                    "name": cleaned,
                    "evidence": [evidence(block)],
                }
    return list(found.values())


def discover_metric_mentions(
    blocks: list[dict[str, Any]], configured: tuple[str, ...]
) -> tuple[list[dict[str, Any]], set[str]]:
    """Discover metric names from result/experiment blocks via patterns.

    Returns found metric dicts and a set of all metric names (configured + discovered).
    """
    relevant = [
        block
        for block in blocks
        if block.get("section_role") in {"results", "experiments", "datasets", "abstract", "methodology"}
        and block.get("type") not in {"header", "footer", "page_number", "page_footnote"}
        and block.get("text", "").strip()
    ]
    # Start with configured mentions
    found = {item["name"].casefold(): item for item in find_mentions(relevant, configured)}
    all_names = {m.casefold() for m in configured}

    # Auto-discover metrics via patterns like "DSC of 0.95", "91.0% mIoU", or "(ASD: 1.25)"
    # Matches true acronyms (>=2 uppercase chars like DSC, HD95, AUC),
    # lowercase-prefixed acronyms (e.g. mIoU, mAP, cDice),
    # or single-letter + digit combinations (e.g. F1, R2).
    metric_token = r"(?:[A-Z]{2,8}[0-9]*|[a-z]{1,2}[A-Z][A-Za-z0-9]{1,6}|[A-Z][0-9]+)"
    auto_patterns = [
        # "METRIC of/= 0.95" or "METRIC: 0.95"
        re.compile(rf"\b({metric_token})\s*(?:of|=|:)\s*\d+\.?\d*"),
        # "0.95 METRIC" or "95.2% METRIC"
        re.compile(rf"\d+\.?\d*\s*%?\s+({metric_token})\b"),
        # Parenthetical "(METRIC: 0.95)" or "(METRIC = 0.95)"
        re.compile(rf"\(\s*({metric_token})\s*[:=]\s*\d+\.?\d*\)"),
    ]
    # Ignore abbreviations that are almost never metric names
    metric_blocklist = {
        "TABLE",
        "FIG",
        "FIGURE",
        "REF",
        "EQ",
        "SEC",
        "SECTION",
        "VOL",
        "NO",
        "PP",
        "ET",
        "AL",
        "IEEE",
        "ACM",
        "MICCAI",
        "CVPR",
        "ICCV",
        "ECCV",
        "NIPS",
        "ICML",
        "AAAI",
        "ARXIV",
        "GPU",
        "CPU",
        "RAM",
        "GAN",
        "CNN",
        "RNN",
        "SAM",
        "BERT",
        "ADAM",
        "SGD",
        "LR",
        "BS",
        "BN",
        "ReLU",
        # Modalities / Medical / Non-metric abbreviations
        "CT",
        "MRI",
        "PET",
        "US",
        "CI",
        "DL",
        "ML",
        "AI",
        "ID",
        "TOTAL",
        "SAMPLE",
        "PATIENT",
        "STUDY",
        "CLASS",
        "GROUP",
        "VERSION",
        "STAGE",
        "PHASE",
        "TYPE",
        "CASE",
        "CASES",
        "ROI",
        "VOI",
        "GT",
        "HU",
        "FOV",
        "TE",
        "TR",
        "SD",
        "SE",
        "NVIDIA",
        "INTEL",
        "AMD",
        "GB",
        "MB",
        "KB",
        "TB",
        "WORD",
    }

    for block in relevant:
        text = block.get("text", "")
        for pattern in auto_patterns:
            for match in pattern.finditer(text):
                name = match.group(1)
                key = name.casefold()
                if key not in found and name.upper() not in metric_blocklist and len(name) >= 2:
                    found[key] = {"name": name, "evidence": [evidence(block)]}
                    all_names.add(key)

    return list(found.values()), all_names


def result_sentences(blocks: list[dict[str, Any]], metrics: tuple[str, ...], limit: int = 20) -> list[dict[str, Any]]:
    """Extract candidate result sentences containing numerical digits and metric keywords."""
    results = []
    metric_pattern = "|".join(re.escape(metric) for metric in metrics)
    # Also match any uppercase abbreviation (2-8 chars) near a number as
    # a fallback — so domain-specific metrics aren't silently dropped.
    combined = metric_pattern + r"|[A-Z][A-Za-z0-9]{1,7}" if metric_pattern else r"[A-Z][A-Za-z0-9]{1,7}"
    for block in blocks:
        if block.get("section_role") not in {"results", "experiments", "datasets"}:
            continue
        for sentence_text in re.split(r"(?<=[.!?])\s+", block.get("text", "")):
            if re.search(r"\d", sentence_text) and re.search(combined, sentence_text):
                results.append(statement(block, sentence_text.strip()))
                if len(results) >= limit:
                    return results
    return results


def analyze_document(
    paper_dir: Path,
    corpus: Path,
    datasets: tuple[str, ...] | None = None,
    metrics: tuple[str, ...] | None = None,
) -> bool:
    """Perform deterministic analysis and evidence extraction on a single normalized document."""
    document = read_json(paper_dir / "document.json", {})
    blocks = read_jsonl(paper_dir / "sections.jsonl") or read_jsonl(paper_dir / "blocks.jsonl")
    if not document or not blocks:
        return False

    if datasets is None or metrics is None:
        default_ds, default_met = load_entities()
        datasets = datasets or default_ds
        metrics = metrics or default_met

    work_id = document["work_id"]
    record_dir = corpus / "records" / work_id
    problem_blocks = select(blocks, {"abstract", "introduction"}, 2)
    method_blocks = select(blocks, {"methodology"}, 6)
    if not method_blocks:
        method_blocks = select(blocks, {"abstract"}, 2)
    experiment_blocks = select(blocks, {"experiments", "datasets"}, 6)
    limitation_blocks = select(blocks, {"limitations", "discussion", "conclusion"}, 3)
    found_datasets = discover_dataset_mentions(blocks, datasets)
    found_metrics, all_metric_names = discover_metric_mentions(blocks, metrics)

    # Extract bibliographic references
    extract_and_save_references(paper_dir, record_dir, document["document_id"])

    existing_work = read_json(record_dir / "work.json", {})
    document_ids = list(existing_work.get("document_ids", []))
    if document["document_id"] not in document_ids:
        document_ids.append(document["document_id"])

    work = {
        "schema_version": "1.0",
        "work_id": work_id,
        "title": document.get("title", paper_dir.name),
        "authors": document.get("authors") or existing_work.get("authors", []),
        "year": document.get("year") or existing_work.get("year"),
        "doi": document.get("doi") or existing_work.get("doi"),
        "arxiv_id": document.get("arxiv_id") or existing_work.get("arxiv_id"),
        "document_ids": sorted(document_ids),
        "merge_status": "title_matched" if len(document_ids) > 1 else "unreviewed",
    }

    analysis = {
        "schema_version": "1.0",
        "work_id": work_id,
        "document_id": document["document_id"],
        "extraction_mode": "deterministic_extractive",
        "research_problem": [statement(block) for block in problem_blocks],
        "methodology": [statement(block) for block in method_blocks],
        "contributions": [],
        "method_components": [],
        "training_objectives": [],
        "limitations": [statement(block) for block in limitation_blocks],
        "claims": [statement(block) for block in select(blocks, {"abstract", "conclusion"}, 5)],
    }

    experiments = {
        "schema_version": "1.0",
        "work_id": work_id,
        "document_id": document["document_id"],
        "datasets": found_datasets,
        "metrics": found_metrics,
        "baselines": [],
        "implementation_details": [statement(block) for block in experiment_blocks],
        "results": result_sentences(blocks, tuple(all_metric_names | set(m.casefold() for m in metrics))),
        "ablations": [
            statement(block) for block in select(blocks, {"results"}, 4) if "ablation" in block.get("text", "").lower()
        ],
    }

    validate_work(work)
    validate_analysis(analysis)
    validate_experiments(experiments)

    document_record_dir = record_dir / "documents" / document["document_id"]
    write_json(record_dir / "work.json", work)
    write_json(document_record_dir / "analysis.json", analysis)
    write_json(document_record_dir / "experiments.json", experiments)
    rebuild_work_aggregates(record_dir, work)
    return True


def rebuild_work_aggregates(record_dir: Path, work: dict[str, Any]) -> None:
    """Recompute work-level aggregated analysis and experiment records from document records."""
    analyses = [read_json(path, {}) for path in sorted((record_dir / "documents").glob("doc_*/analysis.json"))]
    experiments = [read_json(path, {}) for path in sorted((record_dir / "documents").glob("doc_*/experiments.json"))]
    analysis_fields = (
        "research_problem",
        "methodology",
        "contributions",
        "method_components",
        "training_objectives",
        "limitations",
        "claims",
    )
    aggregate_analysis = {
        "schema_version": "1.0",
        "work_id": work["work_id"],
        "document_id": work["document_ids"][0],
        "document_ids": work["document_ids"],
        "extraction_mode": "deterministic_extractive_aggregate",
    }

    def _dedup_items(items: list[dict[str, Any]], key_field: str = "statement") -> list[dict[str, Any]]:
        """Deduplicate items by a text key, keeping the entry with the most evidence."""
        seen: dict[str, dict[str, Any]] = {}
        for item in items:
            text = item.get(key_field) or item.get("name", "")
            k = text.strip().casefold()
            if not k:
                continue
            existing = seen.get(k)
            if existing is None or len(item.get("evidence", [])) > len(existing.get("evidence", [])):
                seen[k] = item
        return list(seen.values())

    for field in analysis_fields:
        aggregate_analysis[field] = _dedup_items([item for value in analyses for item in value.get(field, [])])

    experiment_fields = (
        "datasets",
        "metrics",
        "baselines",
        "implementation_details",
        "results",
        "ablations",
    )
    aggregate_experiments = {
        "schema_version": "1.0",
        "work_id": work["work_id"],
        "document_id": work["document_ids"][0],
        "document_ids": work["document_ids"],
    }
    for field in experiment_fields:
        key_field = "name" if field in ("datasets", "metrics") else "statement"
        aggregate_experiments[field] = _dedup_items(
            [item for value in experiments for item in value.get(field, [])],
            key_field=key_field,
        )

    # Aggregate references
    all_refs = []
    seen_refs = set()
    for ref_path in sorted((record_dir / "documents").glob("doc_*/references.json")):
        ref_data = read_json(ref_path, {})
        for ref_item in ref_data.get("references", []):
            raw = ref_item.get("raw", "").strip()
            if raw and raw not in seen_refs:
                seen_refs.add(raw)
                all_refs.append(ref_item)
    write_json(record_dir / "references.json", {"work_id": work["work_id"], "references": all_refs})

    validate_analysis(aggregate_analysis)
    validate_experiments(aggregate_experiments)
    write_json(record_dir / "analysis.json", aggregate_analysis)
    write_json(record_dir / "experiments.json", aggregate_experiments)


def analyze_corpus(corpus: Path, force: bool = False, entities_path: str | Path | None = None) -> dict[str, int]:
    """Analyze all normalized documents in the corpus."""
    count = skipped = 0
    manifest = load_manifest(corpus)
    records_by_id = {record["document_id"]: record for record in manifest}
    datasets, metrics = load_entities(entities_path)

    for paper_dir in sorted((corpus / "papers").glob("doc_*")):
        document = read_json(paper_dir / "document.json", {})
        if not document:
            continue
        output = corpus / "records" / document["work_id"] / "documents" / document["document_id"] / "analysis.json"
        if output.exists() and not force:
            skipped += 1
            continue
        completed = analyze_document(paper_dir, corpus, datasets=datasets, metrics=metrics)
        count += int(completed)
        if completed and document["document_id"] in records_by_id:
            update_stage(records_by_id[document["document_id"]], "analysis", "complete", mode="deterministic")

    if manifest:
        save_manifest(corpus, manifest)
    logger.info("Corpus analysis finished: %d analyzed, %d skipped", count, skipped)
    return {"documents": count, "skipped": skipped}


ENRICHMENT_FIELDS = (
    "contributions",
    "method_components",
    "training_objectives",
    "limitations",
    "datasets",
    "metrics",
    "results",
)


def enrichment_schema() -> dict[str, Any]:
    """Schema for model-assisted structured fact extraction."""
    item = {
        "type": "object",
        "required": ["statement", "evidence_block_ids"],
        "properties": {
            "statement": {"type": "string"},
            "evidence_block_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        },
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "required": list(ENRICHMENT_FIELDS),
        "properties": {field: {"type": "array", "items": item} for field in ENRICHMENT_FIELDS},
        "additionalProperties": False,
    }


def enrich_document(paper_dir: Path, corpus: Path, provider: Any) -> tuple[bool, str | None]:
    """Enrich document analysis using a local or remote model provider with strict provenance checks."""
    document = read_json(paper_dir / "document.json", {})
    blocks = [block for block in read_jsonl(paper_dir / "sections.jsonl") if substantive(block)]
    if not document or not blocks:
        return False, "No normalized document blocks"

    selected = [
        block
        for block in blocks
        if block.get("section_role")
        in {"abstract", "methodology", "datasets", "experiments", "results", "limitations", "conclusion"}
    ][:80]
    selected = selected or blocks[:40]
    source = "\n\n".join(
        f"BLOCK_ID={block['block_id']} SECTION={block.get('section_role')}\n{block['text'][:1800]}"
        for block in selected
    )[:60000]

    prompt = (
        "Extract only facts explicitly supported by the supplied paper blocks. "
        "Every item must cite one or more exact BLOCK_ID values. Do not infer missing facts. "
        "For datasets and metrics, put the entity name in statement. Return JSON matching the schema.\n\n" + source
    )

    try:
        generated = provider.generate_json(prompt, enrichment_schema())
    except Exception as error:
        return False, str(error)

    by_id = {block["block_id"]: block for block in blocks}

    def block_cited(items: Any) -> list[dict[str, Any]]:
        output = []
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            ids = item.get("evidence_block_ids", [])
            if not item.get("statement") or not ids or any(block_id not in by_id for block_id in ids):
                continue
            output.append(
                {
                    "statement": item["statement"].strip(),
                    "support_status": "evidence_cited_unverified",
                    "evidence": [evidence(by_id[block_id]) for block_id in ids],
                }
            )
        return output

    record_dir = corpus / "records" / document["work_id"]
    document_dir = record_dir / "documents" / document["document_id"]
    analysis = read_json(document_dir / "analysis.json", {})
    experiments = read_json(document_dir / "experiments.json", {})

    for field in ("contributions", "method_components", "training_objectives", "limitations"):
        values = block_cited(generated.get(field, []))
        if values:
            analysis[field] = values

    for field in ("datasets", "metrics"):
        values = block_cited(generated.get(field, []))
        if values:
            experiments[field] = [
                {
                    "name": item["statement"],
                    "evidence": item["evidence"],
                    "support_status": "evidence_cited_unverified",
                }
                for item in values
            ]

    values = block_cited(generated.get("results", []))
    if values:
        experiments["results"] = values

    analysis["extraction_mode"] = "llm_enriched_evidence_validated"
    validate_analysis(analysis)
    validate_experiments(experiments)
    write_json(document_dir / "analysis.json", analysis)
    write_json(document_dir / "experiments.json", experiments)
    work = read_json(record_dir / "work.json", {})
    rebuild_work_aggregates(record_dir, work)
    return True, None


def enrich_corpus(corpus: Path, resolution: Any, force: bool = False) -> dict[str, Any]:
    """Optionally enrich all analyzed documents with model generation."""
    if resolution.effective == "deterministic":
        return {
            "requested": resolution.requested,
            "effective": "deterministic",
            "model": resolution.model,
            "enriched": 0,
            "fallback_reason": resolution.fallback_reason,
        }

    enriched = failed = 0
    errors = []
    manifest = load_manifest(corpus)
    records_by_id = {record["document_id"]: record for record in manifest}

    for paper_dir in sorted((corpus / "papers").glob("doc_*")):
        document = read_json(paper_dir / "document.json", {})
        if not document:
            continue
        record = records_by_id.get(document["document_id"])
        stage = record.get("stages", {}).get("analysis", {}) if record else {}
        if (
            record
            and stage.get("mode") == resolution.effective
            and stage.get("model") == resolution.model
            and not force
        ):
            continue
        ok, error = enrich_document(paper_dir, corpus, resolution.provider)
        if ok:
            enriched += 1
            if record:
                update_stage(record, "analysis", "complete", mode=resolution.effective, model=resolution.model)
        else:
            failed += 1
            errors.append({"document_id": document["document_id"], "error": error})
            if record:
                update_stage(record, "analysis", "complete", mode="deterministic", fallback_reason=error)

    if manifest:
        save_manifest(corpus, manifest)
    return {
        "requested": resolution.requested,
        "effective": resolution.effective if enriched else "deterministic",
        "model": resolution.model,
        "enriched": enriched,
        "failed_with_deterministic_fallback": failed,
        "errors": errors,
    }


def validate_evidence(corpus: Path) -> dict[str, int]:
    """Verify document, block, page, and section coordinates for every evidence locator."""
    valid = invalid = 0
    block_index: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for paper_dir in (corpus / "papers").glob("doc_*"):
        for block in read_jsonl(paper_dir / "sections.jsonl"):
            block_index[block["document_id"]][block["block_id"]] = block

    for path in (corpus / "records").glob("work_*/*.json"):
        value = read_json(path, {})
        stack = [value]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                if "block_id" in item and "document_id" in item:
                    block = block_index.get(item["document_id"], {}).get(item["block_id"])
                    expected_section = " > ".join(block.get("section_path") or []) if block else None
                    coordinates_match = bool(block)
                    if block and "page_index" in item:
                        coordinates_match = coordinates_match and item["page_index"] == block.get("page_index")
                    if block and "section" in item:
                        coordinates_match = coordinates_match and item["section"] == expected_section
                    if coordinates_match:
                        valid += 1
                    else:
                        invalid += 1
                stack.extend(item.values())
            elif isinstance(item, list):
                stack.extend(item)
    return {"valid": valid, "invalid": invalid}
