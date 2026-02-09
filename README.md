# SharePoint Mirror

Mirror SharePoint document libraries locally for browsing, search, and vector database ingestion. Uses Microsoft Graph API delta queries for efficient incremental sync and content-addressed blob storage for deduplication.

## Features

- **Incremental sync** via Graph API delta queries — only fetches changes since the last run
- **Content-addressed storage** — files are deduplicated by SHA256 hash
- **Full-text search** — SQLite FTS5 index on document names and paths
- **Web UI** — browse documents, view PDFs and text files, trigger syncs, review sync history
- **Flexible filtering** — include/exclude by extension, path prefix, or glob pattern
- **Metadata-only mode** — explore a SharePoint site structure without downloading content
- **QuickXorHash verification** — optional integrity check against SharePoint's server-side hashes
- **CLI tools** — sync, export metadata, verify storage, inspect status

## Requirements

- Python 3.14+
- [uv](https://docs.astral.sh/uv/) package manager
- Azure AD app registration with SharePoint read permissions

## Docker Deployment

The `docker-compose.yml` joins a shared Docker network (`platform-net`) for use behind a reverse proxy.

```bash
docker compose build
docker compose up -d
```

Data (SQLite database and blob storage) is persisted in the `sharepoint-mirror-data` Docker volume. Configuration is mounted from `./config.ini`.

## Quick Start (without Docker)

```bash
# Install dependencies
make install

# Copy and edit configuration (instance/ is checked first, project root as fallback)
cp config.ini.example instance/config.ini
# Edit instance/config.ini with your Azure AD credentials and SharePoint site details

# Initialize the database
make init-db

# Test the SharePoint connection
.venv/bin/flask --app wsgi test-connection

# Run your first sync
make do-sync

# Start the web UI
make run
```

## Configuration

Copy `config.ini.example` to `instance/config.ini` (checked first) or `config.ini` in the project root (fallback) and fill in the sections:

### SharePoint Credentials

Register an app in Azure AD with `Sites.Read.All` application permission:

```ini
[sharepoint]
TENANT_ID = your-tenant-id
CLIENT_ID = your-client-id
CLIENT_SECRET = your-client-secret
SITE_HOSTNAME = contoso.sharepoint.com
SITE_PATH = /sites/Documents
# LIBRARY_NAME = Documents  # optional, omit to sync all libraries
```

### Sync Filtering

```ini
[sync]
MAX_FILE_SIZE_MB = 100

# Filter by extension
# INCLUDE_EXTENSIONS = .pdf,.docx,.xlsx
# EXCLUDE_EXTENSIONS = .exe,.zip

# Filter by path prefix (boundary-aware)
# INCLUDE_PATHS =
#     /Projects/Active
#     /Reports/2024

# Glob patterns (first-match-wins, ! prefix = exclude)
# PATH_PATTERNS =
#     *.pdf
#     *.docx
#     !**/~$*
#     !**/drafts/**

# Record metadata without downloading content
# METADATA_ONLY = False

# Verify file integrity using QuickXorHash
# VERIFY_QUICKXOR_HASH = False
```

## Make Targets

| Target | Description |
|---|---|
| `make install` | Install dependencies with uv |
| `make init-db` | Create the database |
| `make migrate-db` | Run pending database migrations |
| `make run` | Start the web server |
| `make rundev` | Start with debug mode |
| `make do-sync` | Run an incremental sync |
| `make do-sync-dry` | Preview sync changes without applying |
| `make do-sync-full` | Full sync (ignore delta tokens) |
| `make status` | Show sync status and statistics |
| `make list` | List synced documents |
| `make check` | Run ruff format/lint + ty typecheck |
| `make clean` | Remove temp files and database |

## CLI Commands

All commands are available through Flask's CLI:

```bash
# Sync
flask --app wsgi sync [--full] [--dry-run] [-l LIBRARY] [-v]

# Status and listing
flask --app wsgi status
flask --app wsgi list [--search TEXT] [--limit N] [--deleted] [--json]

# Export metadata (for vector DB ingestion)
flask --app wsgi export-metadata [-o FILE] [-f json|jsonl] [--include-blob-path]

# Maintenance
flask --app wsgi test-connection
flask --app wsgi clear-delta-tokens
flask --app wsgi verify-storage
```

## Architecture

```
src/sharepoint_mirror/
├── __init__.py              # Flask app factory
├── cli.py                   # CLI commands
├── db.py                    # Database layer (APSW, WAL mode)
├── quickxorhash.py          # QuickXorHash implementation
├── models/                  # Data models
│   ├── document.py          #   SharePoint document metadata
│   ├── file_blob.py         #   Content-addressed blob storage
│   ├── sync_run.py          #   Sync operation records
│   ├── sync_event.py        #   Individual change events
│   └── delta_token.py       #   Graph API delta links
├── services/
│   ├── sharepoint.py        # Microsoft Graph API client
│   ├── storage.py           # Blob storage (SHA256 dedup)
│   └── sync.py              # Sync orchestration
├── blueprints/
│   ├── documents.py         # /documents — browse, search, download
│   ├── sync.py              # /sync — history, trigger syncs
│   └── viewer.py            # /viewer — PDF and text viewers
├── templates/               # Jinja2 + HTMX
└── static/                  # CSS (PicoCSS), JS
```

**Storage layout:** Blobs are stored in `instance/blobs/` using a `{hash[:2]}/{hash[2:4]}/{hash}` directory structure. Identical files across SharePoint are stored once.

**Database:** SQLite via APSW with WAL mode, FTS5 full-text search, foreign keys, and schema migrations.

**Frontend:** Server-rendered templates with HTMX for dynamic updates. No SPA — the web UI works without JavaScript for basic browsing.

## License

[MIT](LICENSE)
