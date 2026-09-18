# ☁️ Setting Up Google Drive Ingestion with rclone

PaperWeave natively supports synchronizing research paper collections directly from Google Drive using [rclone](https://rclone.org/).

---

## 1. Install rclone

### Linux / macOS
```bash
curl https://rclone.org/install.sh | sudo bash
```

### Windows
Download from [rclone downloads](https://rclone.org/downloads/) or via Chocolatey/Winget:
```powershell
winget install Rclone.Rclone
```

Verify installation:
```bash
rclone version
```

---

## 2. Configure Google Drive Remote

Run the interactive rclone setup:

```bash
rclone config
```

Follow the prompts:
1. Type `n` for **New remote**.
2. Enter a name (e.g., `mydrive` or `gdrive`).
3. For storage type, type `drive` (Google Drive).
4. Leave `client_id` and `client_secret` blank (or provide your own GCP OAuth credentials).
5. For scope, choose `1` (Full access to all files).
6. Leave `root_folder_id` and `service_account_file` blank.
7. For `Edit advanced config`, choose `n`.
8. For `Use web browser to authenticate`, choose `y` (a browser window will open to sign in with your Google account).
9. Confirm and choose `q` to quit config.

---

## 3. Verify Connection

List the top-level directories in your Google Drive:

```bash
rclone lsd mydrive:
```

If your folders are listed, your connection is verified and ready.

---

## 4. Run PaperWeave with Google Drive

Pass the Google Drive folder URL directly to `paperweave run` along with the `--remote` name:

```bash
paperweave run "https://drive.google.com/drive/folders/11hb5QMKcP1uvO9Qj1wk9ZQik9ac7Pnxe" --remote mydrive
```

### What PaperWeave does automatically:
- Connects to the specified remote folder via rclone.
- Downloads papers to a local staging area.
- Content-hashes each document with SHA-256 to prevent duplicate downloads.
- Runs full MinerU extraction, sectioning, semantic synthesis, and knowledge graph generation.
- Leaves your original Google Drive files completely untouched.
