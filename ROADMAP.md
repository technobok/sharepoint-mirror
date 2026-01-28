# SharePoint Mirror - Development Roadmap

## Status Legend
- [ ] Pending
- [~] In Progress
- [x] Done

---

## Phase 1: Project Foundation

- [x] Create directory structure
- [x] Create pyproject.toml
- [x] Create Makefile
- [x] Create config.ini.example
- [x] Create .gitignore
- [x] Create src/sharepoint_mirror/__init__.py (app factory)
- [x] Create src/sharepoint_mirror/db.py
- [x] Create database/schema.sql
- [x] Create wsgi.py

---

## Phase 2: Core Services

- [x] Create services/storage.py - hash-based blob storage
- [x] Create services/sharepoint.py - Graph API client with auth
- [x] Create services/sync.py - sync orchestration
- [ ] Test authentication against real SharePoint

---

## Phase 3: Models

- [x] Create models/__init__.py
- [x] Create models/file_blob.py
- [x] Create models/document.py
- [x] Create models/sync_run.py
- [x] Create models/sync_event.py
- [x] Create models/delta_token.py

---

## Phase 4: CLI Commands

- [x] Register CLI commands in app factory
- [x] Implement init-db command
- [x] Implement sync command (with --full and --dry-run)
- [x] Implement status command
- [x] Implement list command
- [x] Implement export-metadata command
- [x] Implement test-connection command
- [x] Implement clear-delta-tokens command
- [x] Implement verify-storage command
- [ ] Test full sync against real SharePoint

---

## Phase 5: Webapp

- [x] Complete Flask app factory
- [x] Create blueprints/documents.py
- [x] Create blueprints/sync.py
- [x] Create blueprints/viewer.py
- [x] Create templates/base.html
- [x] Create templates/index.html (dashboard)
- [x] Create templates/documents/ (index, view, list partial)
- [x] Create templates/sync/ (index, view, history partial, status partial)
- [x] Create templates/viewer/ (pdf, text)
- [x] Create static/css/app.css (PicoCSS customization)
- [x] Create static/js/app.js

---

## Phase 6: PDF Viewer

- [x] Create templates/viewer/pdf.html (using browser's built-in PDF viewer)
- [x] Add blob serving route for documents
- [ ] Optional: Add pdf.js for more features

---

## Phase 7: Polish

- [ ] Run ruff format on all files
- [ ] Run ruff lint and fix issues
- [ ] Run ty typecheck and fix issues
- [ ] Write tests for sync service
- [ ] Write tests for storage service
- [ ] Test full end-to-end workflow

---

## Notes & Decisions

### 2026-01-28
- Using browser's built-in PDF viewer via iframe instead of pdf.js for simplicity
- Delta query approach using Microsoft Graph API for efficient incremental syncs
- Content-addressed storage with 2-level directory structure (hash[:2]/hash[2:4]/hash)
- Soft delete for documents to preserve history
- modify_remove + modify_add event pairs for tracking content changes

---

## Changelog

### 2026-01-28
- [Phase 1-6] Initial implementation complete
- Created project structure following cadence patterns
- Implemented APSW database layer with FTS5 search
- Implemented Microsoft Graph API client with delta queries
- Implemented content-addressed blob storage
- Implemented sync orchestration service
- Created CLI commands: init-db, sync, status, list, export-metadata, test-connection, clear-delta-tokens, verify-storage
- Created Flask webapp with HTMX
- Created document browsing, sync management, and PDF/text viewer
- Added PicoCSS styling with dark mode support
