"""Inference provider resolution (deterministic, Ollama, OpenAI-compatible) and hardware probes."""

from __future__ import annotations

import json
import logging
import os
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
    """Detect available compute resources (NVIDIA GPU, CUDA, Ollama CLI)."""
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

    return {"gpu": gpu, "ollama_command": bool(shutil.which("ollama"))}


@dataclass
class ProviderResolution:
    """Result of resolving the requested inference provider."""

    requested: str
    effective: str
    provider: Any = None
    fallback_reason: str | None = None


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

    return ProviderResolution(kind, kind, provider=provider)
