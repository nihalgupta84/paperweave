# 🦙 Setting Up Local LLMs (Ollama & llm-checker)

PaperWeave is 100% offline-first. It can leverage local LLMs via [Ollama](https://ollama.com/) to enrich extracted summaries with zero cloud dependencies, or run in pure deterministic mode without any LLM.

---

## 1. Install Ollama

### Linux
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### macOS
Download from [ollama.com/download](https://ollama.com/download) or install via Homebrew:
```bash
brew install ollama
```

### Windows
Download the Windows installer from [ollama.com/download/windows](https://ollama.com/download/windows).

---

## 2. Pull Recommended Models

We recommend models with strong instruction-following and structured output capabilities:

```bash
# Recommended default (balanced speed & accuracy)
ollama pull qwen2.5:7b

# Alternative high-performing options
ollama pull llama3.1:8b
ollama pull mistral:7b
```

Verify that the model is running:
```bash
ollama list
```

---

## 3. Install llm-checker (for Auto-Selection)

PaperWeave uses `llm-checker` to automatically discover, test, and rank installed local models based on your hardware capabilities:

```bash
python -m pip install llm-checker
```

---

## 4. Verify Capabilities

Run the PaperWeave diagnostics command:

```bash
paperweave capabilities
```

Output will show:
- GPU availability and VRAM
- MinerU PDF pipeline status
- Ollama service status and detected local models
- Preferred model ranked by `llm-checker`

---

## 5. Running PaperWeave with Local Models

### Automatic Selection (Recommended)
Let PaperWeave pick the best available local model:
```bash
paperweave run ./papers --semantic-provider auto
```

### Explicit Model Specification
```bash
paperweave run ./papers --semantic-provider ollama --model qwen2.5:7b
```

### Pure Deterministic Mode (No GPU / No LLM Required)
If you don't have a GPU or prefer 100% rule-based deterministic extraction:
```bash
paperweave run ./papers --semantic-provider deterministic
```
*(All extractions remain fully grounded with exact `[doc:block:page]` locators regardless of mode.)*
