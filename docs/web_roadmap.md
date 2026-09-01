# PaperWeave Web and Connector Roadmap

## Goal

Provide the same evidence-first corpus workflow through a local or secured web
interface without making cloud services, GPUs, or external storage mandatory.

```text
local folder ─┐
              ├─> ingestion jobs -> PaperWeave records/indexes/graphs -> web UI
Google Drive ─┘
                                                               │
                                      localhost or Cloudflare Tunnel
```

## Release sequence

### v0.3 — Local single-user web application

- FastAPI service wrapping existing pipeline functions and background jobs.
- Upload or select a configured local corpus; never accept arbitrary server
  filesystem paths from remote clients.
- Corpus dashboard, document status, synthesis reader, search, evidence drawer,
  duplicate review, and interactive paper graph.
- Job progress, cancellation boundaries, durable state, and readable failure
  messages for MinerU/GROBID/model stages.
- Bind to `127.0.0.1` by default with no telemetry.

Acceptance: a user can ingest two local papers, inspect related-paper links,
search blocks, open evidence, and regenerate reports entirely through the UI.

### v0.4 — Google Drive connector

- Keep the existing rclone import for local/CLI users.
- Add an optional Google OAuth connector for the web application with read-only
  Drive scope by default, explicit folder selection, token encryption, and
  revocation.
- Download to a per-corpus staging area, then run the same hash deduplication
  path used for local files.
- Record Drive file ID, revision, checksum, and import time for incremental sync.
- Never write back, rename, or delete Drive files without a separate explicit
  permission and user action.

Acceptance: repeated imports process only new/changed supported documents and
do not duplicate unchanged Drive files.

### v0.5 — Secured remote access through Cloudflare

- Provide a documented `cloudflared` deployment profile routing to the local
  web service.
- Require Cloudflare Access or equivalent authentication before advertising a
  public hostname. A tunnel alone does not provide application authorization.
- Enforce upload limits, MIME/signature checks, rate limits, CSRF protection,
  secure cookies, audit logs, and per-user/per-corpus authorization.
- Disable arbitrary local-path ingestion for remote sessions.
- Add a queue and concurrency limits so MinerU or LLM jobs cannot exhaust the
  host. Show users whether jobs run on CPU, GPU, or an external endpoint.

Acceptance: an unauthenticated visitor cannot access corpora or start jobs, and
two authorized users cannot access each other's documents.

### v0.6 — Hosted multi-user service

- Separate API, worker, metadata database, and object storage deployments.
- Isolated workspaces, quotas, retention controls, deletion/export workflows,
  and administrator observability.
- Optional Qdrant/neural embeddings and external scholarly graph enrichment.
- Deployment templates may support Cloudflare, but the core remains portable.

## UI information architecture

1. **Corpora** — local/Drive sources, counts, pipeline state, failures.
2. **Papers** — canonical works, versions, metadata conflicts, quality review.
3. **Explore** — hybrid search and faceted collections.
4. **Map** — citation, related-paper, dataset, and taxonomy graph layers.
5. **Synthesis** — methodology, experiments, datasets, literature review,
   references, and combined text.
6. **Evidence** — source block, page, section, parser, and support status.

## Non-negotiable boundaries

- Paper files and extracted text remain private unless the user deliberately
  shares them and has redistribution rights.
- A computed related-paper edge is never displayed as a citation.
- Candidate citation matches remain visibly unverified.
- Web narratives must retain evidence locators and model-generated claims must
  remain marked semantically unverified.
- Cloudflare Tunnel exposes an operator's running service; it does not itself
  turn PaperWeave into a safe public multi-tenant product.
