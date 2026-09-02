"""Inference provider resolution (deterministic, Ollama, OpenAI-compatible) and hardware probes."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


def request_json(
    url: str,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 10,
) -> Any:
    """Send an HTTP request and deserialize JSON response."""
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


def compute_capabilities() -> dict[str, Any]:
    """Detect available compute resources and optional workflow commands."""
    gpu = {"available": False, "name": None, "memory_mb": None}
    if shutil.which("nvidia-smi"):
        try:
            output = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            ).stdout.splitlines()
            if output and "," in output[0] and output[0].rsplit(",", 1)[-1].strip().isdigit():
                name, memory = output[0].rsplit(",", 1)
                gpu = {"available": True, "name": name.strip(), "memory_mb": int(memory.strip())}
        except Exception as e:
            logger.debug("nvidia-smi query failed: %s", e)

    if not gpu["available"]:
        try:
            import torch

            if torch.cuda.is_available():
                properties = torch.cuda.get_device_properties(0)
                gpu = {
                    "available": True,
                    "name": torch.cuda.get_device_name(0),
                    "memory_mb": round(properties.total_memory / (1024 * 1024)),
                }
        except Exception as e:
            logger.debug("torch cuda check failed: %s", e)

    return {
        "gpu": gpu,
        "commands": {
            "mineru": shutil.which("mineru"),
            "rclone": shutil.which("rclone"),
            "ollama": shutil.which("ollama"),
            "llm_checker": shutil.which("llm-checker"),
        },
        "ollama_command": bool(shutil.which("ollama")),
    }


@dataclass
class ProviderResolution:
    """Result of resolving the requested inference provider."""

    requested: str
    effective: str
    provider: Any = None
    fallback_reason: str | None = None
    model: str | None = None


def _json_fragment(value: str) -> Any:
    """Decode JSON even when a CLI writes progress text before it."""
    value = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", value)
    decoder = json.JSONDecoder()
    for position, character in enumerate(value):
        if character in "[{":
            try:
                parsed, _ = decoder.raw_decode(value[position:])
                return parsed
            except json.JSONDecodeError:
                continue
    return None


def _model_candidates(value: Any) -> list[tuple[float, str]]:
    candidates: list[tuple[float, str]] = []
    if isinstance(value, dict):
        name = next((value.get(key) for key in ("model", "name", "modelName", "model_name") if value.get(key)), None)
        if isinstance(name, str):
            score_value = next(
                (value.get(key) for key in ("score", "totalScore", "compatibility") if value.get(key) is not None), 0
            )
            try:
                score = float(score_value)
            except (TypeError, ValueError):
                score = 0.0
            candidates.append((score, name))
        for child in value.values():
            candidates.extend(_model_candidates(child))
    elif isinstance(value, list):
        for child in value:
            candidates.extend(_model_candidates(child))
    return candidates


def select_ollama_model_with_llm_checker(base_url: str = "http://127.0.0.1:11434") -> tuple[str | None, str | None]:
    """Select the best already-installed Ollama model ranked by llm-checker."""
    checker = shutil.which("llm-checker")
    if not checker:
        return None, "llm-checker is not installed"
    try:
        tags = request_json(f"{base_url.rstrip('/')}/api/tags", timeout=5)
        installed = {str(item.get("name")) for item in tags.get("models", []) if item.get("name")}
    except Exception as error:
        return None, f"Ollama is unavailable: {error}"
    if not installed:
        return None, "Ollama has no installed models"
    try:
        environment = os.environ.copy()
        environment["OLLAMA_HOST"] = base_url
        completed = subprocess.run(
            [checker, "installed", "--json"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return None, f"llm-checker failed: {error}"
    payload = _json_fragment(completed.stdout)
    ranked = sorted(_model_candidates(payload), reverse=True)
    for _, candidate in ranked:
        if candidate in installed:
            return candidate, None
        matches = [name for name in installed if name == candidate or name.startswith(f"{candidate}:")]
        if matches:
            return sorted(matches)[0], None
    detail = (completed.stderr or completed.stdout).strip().splitlines()
    reason = detail[-1] if detail else "llm-checker returned no installed-model recommendation"
    return None, reason


class OllamaProvider:
    """Ollama local model endpoint client."""

    def __init__(self, model: str, base_url: str = "http://127.0.0.1:11434") -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")

    def probe(self) -> tuple[bool, str | None]:
        """Verify endpoint connectivity and model availability."""
        try:
            value = request_json(f"{self.base_url}/api/tags")
            models = {item.get("name") for item in value.get("models", [])}
            if self.model not in models and not any(name and name.startswith(f"{self.model}:") for name in models):
                return False, f"Ollama model is not installed: {self.model}"
            return True, None
        except Exception as error:
            return False, f"Ollama endpoint unavailable: {error}"

    def generate_json(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Generate structured JSON adhering to the provided JSON Schema."""
        value = request_json(
            f"{self.base_url}/api/generate",
            {"model": self.model, "prompt": prompt, "format": schema, "stream": False},
            timeout=300,
        )
        return json.loads(value["response"])


class OpenAICompatibleProvider:
    """Generic OpenAI-compatible inference client (vLLM, Ollama, LM Studio, etc.)."""

    def __init__(self, model: str, base_url: str, api_key_env: str = "OPENAI_API_KEY") -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = os.environ.get(api_key_env, "")

    @property
    def headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def probe(self) -> tuple[bool, str | None]:
        """Verify endpoint connectivity."""
        try:
            request_json(f"{self.base_url}/models", headers=self.headers)
            return True, None
        except Exception as error:
            return False, f"OpenAI-compatible endpoint unavailable: {error}"

    def generate_json(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Generate structured JSON adhering to the provided JSON Schema."""
        value = request_json(
            f"{self.base_url}/chat/completions",
            {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "paper_analysis", "strict": True, "schema": schema},
                },
                "temperature": 0,
            },
            headers=self.headers,
            timeout=300,
        )
        return json.loads(value["choices"][0]["message"]["content"])


def resolve_provider(
    kind: str,
    model: str | None,
    base_url: str | None,
    strict: bool = False,
) -> ProviderResolution:
    """Resolve requested semantic provider with automatic graceful fallback to deterministic mode."""
    if kind in {"none", "deterministic"}:
        return ProviderResolution(kind, "deterministic")
    if kind == "auto":
        ollama_url = base_url or "http://127.0.0.1:11434"
        selected, reason = (model, None) if model else select_ollama_model_with_llm_checker(ollama_url)
        if not selected:
            if strict:
                raise RuntimeError(reason or "No local semantic model is available")
            return ProviderResolution("auto", "deterministic", fallback_reason=reason)
        provider = OllamaProvider(selected, ollama_url)
        available, probe_reason = provider.probe()
        if not available:
            if strict:
                raise RuntimeError(probe_reason)
            return ProviderResolution("auto", "deterministic", fallback_reason=probe_reason)
        return ProviderResolution("auto", "ollama", provider=provider, model=selected)
    if not model:
        reason = "No semantic model was specified"
        if strict:
            raise RuntimeError(reason)
        return ProviderResolution(kind, "deterministic", fallback_reason=reason)

    if kind == "ollama":
        provider = OllamaProvider(model, base_url or "http://127.0.0.1:11434")
    elif kind == "openai-compatible":
        provider = OpenAICompatibleProvider(model, base_url or "http://127.0.0.1:8000/v1")
    else:
        raise ValueError(f"Unknown provider: {kind}")

    available, reason = provider.probe()
    if not available:
        if strict:
            raise RuntimeError(reason)
        return ProviderResolution(kind, "deterministic", fallback_reason=reason)

    return ProviderResolution(kind, kind, provider=provider, model=model)
