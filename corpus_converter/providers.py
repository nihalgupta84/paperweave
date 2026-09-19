"""Inference provider resolution (deterministic, Ollama, OpenAI-compatible) and hardware probes."""

from __future__ import annotations

import json
import logging
import os
import platform
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

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


def _mineru_version(command: str) -> str | None:
    try:
        output = subprocess.run([command, "--version"], check=False, text=True, capture_output=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = re.search(r"\d+(?:\.\d+)+", f"{output.stdout} {output.stderr}")
    return match.group(0) if match else None


def resolve_mineru_command(explicit: str | os.PathLike[str] | None = None) -> tuple[str | None, str | None]:
    """Find a functional MinerU binary (version 3.x), inspecting explicit paths, env vars, known conda envs, and PATH."""
    candidates: list[str] = []
    if explicit:
        candidates.append(str(explicit))
    if os.environ.get("MINERU_BIN"):
        candidates.append(os.environ["MINERU_BIN"])
    if os.environ.get("MINERU_PATH"):
        candidates.append(os.environ["MINERU_PATH"])

    from pathlib import Path

    known_conda_paths = [
        "/workspace/miniconda3/envs/mineru/bin/mineru",
        str(Path.home() / "miniconda3/envs/mineru/bin/mineru"),
        str(Path.home() / ".conda/envs/mineru/bin/mineru"),
        "/opt/conda/envs/mineru/bin/mineru",
    ]
    for kp in known_conda_paths:
        if os.path.isfile(kp) and os.access(kp, os.X_OK):
            candidates.append(kp)

    which_cmd = shutil.which("mineru")
    if which_cmd and which_cmd not in candidates:
        candidates.append(which_cmd)

    v3_candidate = None
    v4_candidate = None

    for cand in candidates:
        if not (os.path.isfile(cand) and os.access(cand, os.X_OK)):
            continue
        ver = _mineru_version(cand)
        if ver and ver.startswith("3."):
            return cand, ver
        elif ver and ver.startswith("4."):
            if not v4_candidate:
                v4_candidate = (cand, ver)
        else:
            try:
                proc = subprocess.run([cand, "--help"], capture_output=True, text=True, timeout=10)
                txt = f"{proc.stdout} {proc.stderr}"
            except Exception:
                txt = ""
            if "-p, --path" in txt or "--path" in txt:
                return cand, ver
            elif "COMMAND [ARGS]" in txt and "parse" in txt:
                if not v4_candidate:
                    v4_candidate = (cand, ver)
            elif not v3_candidate:
                v3_candidate = (cand, ver)

    if v3_candidate:
        return v3_candidate
    if v4_candidate:
        return v4_candidate
    return None, None


def detect_system_vram_and_hardware() -> tuple[int, int, str, str]:
    """Detect available VRAM/RAM (free_mb, total_mb), backend type, and device name without external heavy dependencies."""
    # 1. NVIDIA GPU via nvidia-smi
    if shutil.which("nvidia-smi"):
        try:
            output = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            ).stdout.splitlines()
            if output and "," in output[0]:
                parts = [p.strip() for p in output[0].split(",")]
                if len(parts) >= 3 and parts[1].isdigit() and parts[2].isdigit():
                    name = parts[0]
                    total_mb = int(parts[1])
                    free_mb = int(parts[2])
                    return free_mb, total_mb, "cuda", name
                elif len(parts) >= 1 and parts[0]:
                    # In MIG mode or container restrictions, parse raw nvidia-smi table
                    raw_txt = subprocess.check_output(["nvidia-smi"], text=True, timeout=5)
                    mig_match = re.search(r"(\d+)\s*MiB\s*/\s*(\d+)\s*MiB", raw_txt)
                    if mig_match:
                        used_mb = int(mig_match.group(1))
                        total_mb = int(mig_match.group(2))
                        free_mb = max(0, total_mb - used_mb)
                        return free_mb, total_mb, "cuda", parts[0]
        except Exception as e:
            logger.debug("nvidia-smi VRAM probe failed: %s", e)

    # 2. PyTorch CUDA fallback
    try:
        import torch

        if torch.cuda.is_available():
            dev_idx = torch.cuda.current_device()
            name = torch.cuda.get_device_name(dev_idx)
            free_b, total_b = torch.cuda.mem_get_info(dev_idx)
            return round(free_b / (1024 * 1024)), round(total_b / (1024 * 1024)), "cuda", name
    except Exception as e:
        logger.debug("torch cuda probe failed: %s", e)

    # 3. Apple Silicon (Darwin / ARM) Unified Memory
    if platform.system() == "Darwin" and platform.processor() == "arm":
        try:
            mem_str = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True, timeout=5).strip()
            total_mb = round(int(mem_str) / (1024 * 1024))
            free_mb = round(total_mb * 0.65)
            return free_mb, total_mb, "metal", "Apple Silicon Unified Memory"
        except Exception as e:
            logger.debug("sysctl memsize probe failed: %s", e)

    # 4. CPU / Host System RAM fallback
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        total_mb = round((pages * page_size) / (1024 * 1024))
        try:
            avail_pages = os.sysconf("SC_AVPHYS_PAGES")
            free_mb = round((avail_pages * page_size) / (1024 * 1024))
        except Exception:
            free_mb = round(total_mb * 0.5)
        return free_mb, total_mb, "cpu", "CPU System Memory"
    except Exception:
        pass

    return 4096, 8192, "cpu", "Generic Host Memory"


def select_optimal_model_for_vram(free_mb: int, backend: str = "cuda") -> tuple[str, str]:
    """Select the highest-quality LLM variant that safely maximizes utilization within the available VRAM envelope."""
    # First: if llm-checker is installed, query its recommendation
    checker = shutil.which("llm-checker")
    if checker:
        try:
            cmd = [checker, "smart-recommend", "--json", "--limit", "3"]
            res = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=15)
            payload = _json_fragment(res.stdout)
            if isinstance(payload, dict) and payload.get("recommendations"):
                top = payload["recommendations"][0]
                tag = top.get("variant", {}).get("tag")
                if tag:
                    return tag, f"llm-checker hardware recommendation ({tag})"
        except Exception as err:
            logger.debug("llm-checker smart-recommend failed: %s", err)

    # For CPU execution, throttle model size so inference doesn't stall
    if backend == "cpu":
        if free_mb >= 16000:
            return "qwen2.5-coder:7b-instruct-q8_0", f"CPU host memory ({free_mb} MB) -> 7B Q8"
        elif free_mb >= 8000:
            return "qwen2.5:3b", f"CPU host memory ({free_mb} MB) -> 3B"
        else:
            return "qwen2.5:1.5b", f"CPU host memory ({free_mb} MB) -> 1.5B"

    # GPU (CUDA / Metal) hardware-aware model envelope
    if free_mb >= 30000:
        return "qwen2.5-coder:14b-instruct-q8_0", f"High VRAM ({free_mb} MB) -> 14B Q8"
    elif free_mb >= 14000:
        return "qwen2.5-coder:14b-instruct-q6_K", f"Mid-high VRAM ({free_mb} MB) -> 14B Q6_K"
    elif free_mb >= 7000:
        return "qwen2.5-coder:7b-instruct-q8_0", f"Mid VRAM ({free_mb} MB) -> 7B Q8"
    elif free_mb >= 4000:
        return "qwen2.5:3b", f"Low VRAM ({free_mb} MB) -> 3B"
    else:
        return "qwen2.5:1.5b", f"Minimal VRAM/RAM ({free_mb} MB) -> 1.5B"


def ensure_ollama_service_and_model(
    model: str,
    base_url: str = "http://127.0.0.1:11434",
    auto_pull: bool = True,
) -> tuple[bool, Callable[[], None] | None, str | None]:
    """Ensure Ollama is running and the specified model is ready.

    If the server is not running, launches an ephemeral background process and returns a cleanup callback.
    If the model is not downloaded, pulls it automatically.
    """
    ollama_cmd = shutil.which("ollama")
    cleanup_fn: Callable[[], None] | None = None
    server_ready = False

    # 1. Check if server is already responding
    try:
        request_json(f"{base_url.rstrip('/')}/api/tags", timeout=2)
        server_ready = True
    except Exception:
        server_ready = False

    # 2. If not running, attempt to spawn ephemeral background server (only for default local endpoint)
    if not server_ready:
        is_default_local = base_url.rstrip("/") in {"http://127.0.0.1:11434", "http://localhost:11434"}
        if not is_default_local:
            return False, None, f"Ollama endpoint unavailable at {base_url}"

        if not ollama_cmd:
            return False, None, "Ollama CLI is not installed (install from https://ollama.com to enable local LLM)"

        try:
            env = os.environ.copy()
            proc = subprocess.Popen(
                [ollama_cmd, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
            )

            # Poll for readiness up to 10 seconds
            start_time = time.time()
            while time.time() - start_time < 10:
                time.sleep(0.5)
                try:
                    request_json(f"{base_url.rstrip('/')}/api/tags", timeout=2)
                    server_ready = True
                    break
                except Exception:
                    continue

            if not server_ready:
                try:
                    proc.terminate()
                    proc.wait(timeout=2)
                except Exception:
                    proc.kill()
                return False, None, f"Ollama server started but endpoint remains unavailable at {base_url}"

            def _cleanup() -> None:
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass

            cleanup_fn = _cleanup
        except Exception as e:
            return False, None, f"Failed to launch Ollama server: {e}"

    # 3. Check if model is downloaded; pull if missing
    try:
        tags = request_json(f"{base_url.rstrip('/')}/api/tags", timeout=5)
        installed = {str(item.get("name")) for item in tags.get("models", []) if item.get("name")}
    except Exception as e:
        if cleanup_fn:
            cleanup_fn()
        return False, None, f"Failed to list models from Ollama: {e}"

    model_present = (
        model in installed
        or any(name.startswith(f"{model}:") or model.startswith(f"{name}:") for name in installed)
    )

    if not model_present:
        if not auto_pull or not ollama_cmd:
            if cleanup_fn:
                cleanup_fn()
            return False, None, f"Model '{model}' is not installed in Ollama"

        logger.info("Local model '%s' not cached. Automatically pulling via Ollama...", model)
        try:
            subprocess.run([ollama_cmd, "pull", model], check=True, timeout=600)
        except Exception as e:
            if cleanup_fn:
                cleanup_fn()
            return False, None, f"Failed to pull model '{model}': {e}"

    return True, cleanup_fn, None


def compute_capabilities() -> dict[str, Any]:
    """Detect available compute resources, VRAM budget, and optimal workflow commands."""
    free_mb, total_mb, backend, dev_name = detect_system_vram_and_hardware()
    recommended_model, rec_reason = select_optimal_model_for_vram(free_mb, backend)
    gpu = {
        "available": backend in {"cuda", "metal"},
        "name": dev_name,
        "memory_mb": total_mb,
        "free_memory_mb": free_mb,
        "backend": backend,
        "recommended_model": recommended_model,
        "model_selection_reason": rec_reason,
    }

    mineru_cmd, mineru_ver = resolve_mineru_command()
    return {
        "gpu": gpu,
        "commands": {
            "mineru": mineru_cmd,
            "mineru_version": mineru_ver,
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
    cleanup_fn: Any = None

    def cleanup(self) -> None:
        """Terminate any ephemeral background services spawned during this session."""
        if callable(self.cleanup_fn):
            try:
                self.cleanup_fn()
            except Exception as err:
                logger.debug("Provider cleanup failed: %s", err)
            finally:
                self.cleanup_fn = None


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

    if kind in {"auto", "auto-local"}:
        ollama_url = base_url or "http://127.0.0.1:11434"
        selected = model
        selection_reason = None

        if not selected:
            # 1. If server is already active with installed models, rank them
            selected, selection_reason = select_ollama_model_with_llm_checker(ollama_url)
            if selected:
                provider = OllamaProvider(selected, ollama_url)
                available, probe_reason = provider.probe()
                if available:
                    return ProviderResolution(kind, "ollama", provider=provider, model=selected)

            # 2. Otherwise, autonomously choose optimal model by VRAM envelope
            free_mb, total_mb, backend, dev_name = detect_system_vram_and_hardware()
            selected, selection_reason = select_optimal_model_for_vram(free_mb, backend)

        if not selected:
            if strict:
                raise RuntimeError(selection_reason or "No local semantic model is available")
            return ProviderResolution(kind, "deterministic", fallback_reason=selection_reason)

        ok, cleanup_fn, err = ensure_ollama_service_and_model(selected, ollama_url)
        if not ok:
            if strict:
                raise RuntimeError(err or "Failed to initialize local LLM")
            logger.info("Local LLM not available: %s. Using deterministic grounded extraction.", err)
            return ProviderResolution(kind, "deterministic", fallback_reason=err)

        provider = OllamaProvider(selected, ollama_url)
        available, probe_reason = provider.probe()
        if not available:
            if cleanup_fn:
                cleanup_fn()
            if strict:
                raise RuntimeError(probe_reason)
            return ProviderResolution(kind, "deterministic", fallback_reason=probe_reason)

        return ProviderResolution(kind, "ollama", provider=provider, model=selected, cleanup_fn=cleanup_fn)

    if not model:
        reason = "No semantic model was specified"
        if strict:
            raise RuntimeError(reason)
        return ProviderResolution(kind, "deterministic", fallback_reason=reason)

    if kind == "ollama":
        ollama_url = base_url or "http://127.0.0.1:11434"
        ok, cleanup_fn, err = ensure_ollama_service_and_model(model, ollama_url)
        if not ok:
            if strict:
                raise RuntimeError(err)
            return ProviderResolution(kind, "deterministic", fallback_reason=err)
        provider = OllamaProvider(model, ollama_url)
        available, probe_reason = provider.probe()
        if not available:
            if cleanup_fn:
                cleanup_fn()
            if strict:
                raise RuntimeError(probe_reason)
            return ProviderResolution(kind, "deterministic", fallback_reason=probe_reason)
        return ProviderResolution(kind, "ollama", provider=provider, model=model, cleanup_fn=cleanup_fn)

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
