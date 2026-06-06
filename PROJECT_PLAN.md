# PROJECT_PLAN.md — npm-sentinel

## Project Title

**NPM Sentinel — Package Intelligence Scanner**

## Purpose

This document defines the execution plan for building `npm-sentinel`, a production-shaped NPM package intelligence scanner for the OX Security home assignment.

The scanner must collect NPM package metadata, compare the latest package version with one previous version, detect suspicious supply-chain indicators, calculate a risk score from 1 to 100, persist results in a database, continuously monitor package updates, and run through a single Docker Compose command with 3 to 5 services, including a database and a queue.

This document is the implementation backlog and delivery plan. Engineering rules, architecture constraints, and code quality standards should live in `AGENTS.md`.

---

## Target Architecture

Use a **FastAPI modular monolith** with separate runtime processes:

```text
api        → FastAPI HTTP service
worker     → Celery scan worker
scheduler  → update monitor / job producer
postgres   → durable database
rabbitmq   → durable queue / message broker
```

The API, worker, and scheduler share the same codebase, domain logic, application use cases, and infrastructure adapters.

The worker layer should be stateless and horizontally scalable:

```bash
docker compose up --scale worker=4
```

RabbitMQ holds pending jobs. PostgreSQL stores durable scan intelligence. Workers use temporary local storage only during static package analysis and delete raw package files after each scan.

---

## Core Design Principles

- Build a working vertical slice first, then improve it.
- Keep the project as a modular monolith, not microservices.
- Use RabbitMQ/Celery for asynchronous scan job processing.
- Use PostgreSQL as the source of truth.
- Keep FastAPI routes thin.
- Keep scanning logic out of the API process.
- Use bounded concurrency, not unlimited async execution.
- Use temporary directories for package downloads/extraction.
- Never execute NPM package code.
- Use static analysis only.
- Persist failures instead of silently losing them.
- Make queue processing idempotent.
- Add tests for core logic and persistence behavior.
- Keep implementation simple enough to finish quickly, but clean enough to look senior.

---

## Execution Model: Async, Concurrency, and Parallelism

The project uses three execution styles intentionally.

### 1. Async I/O

Use async I/O for network-bound operations:

- Fetching NPM registry metadata
- Downloading package tarballs
- Scheduler metadata checks
- API handlers where useful

Recommended tools:

- `httpx.AsyncClient`
- request timeouts
- `asyncio.Semaphore` for bounded concurrency

Do not use unbounded `asyncio.gather()` across hundreds or thousands of packages.

### 2. Celery Worker Concurrency

Use Celery/RabbitMQ as the main concurrency mechanism for package scans.

Example:

```bash
celery -A app.infrastructure.queue.celery_app worker --loglevel=info --concurrency=5
```

This allows multiple package scan jobs to run in parallel inside one worker container.

The worker service can also be horizontally scaled:

```bash
docker compose up --scale worker=4
```

This allows multiple worker containers to consume jobs from the same RabbitMQ queue.

### 3. Synchronous Local Analysis

Keep local static analysis functions synchronous and simple:

- Tarball extraction
- Package JSON reading
- File walking
- Binary detection
- Obfuscation detection
- Command execution detection
- Size comparison
- Scoring
- Repository methods, unless async SQLAlchemy is intentionally selected

Do not manually create threads or multiprocessing pools for the assignment version. Celery concurrency is enough.

---

## Recommended Project Structure

```text
npm-sentinel/
  AGENTS.md
  PROJECT_PLAN.md
  README.md
  Dockerfile
  docker-compose.yml
  pyproject.toml
  alembic.ini
  .env.example

  app/
    __init__.py
    main.py

    api/
      __init__.py
      dependencies.py
      schemas.py
      routes/
        __init__.py
        health.py
        scans.py
        packages.py
        findings.py

    domain/
      __init__.py
      entities.py
      enums.py
      findings.py
      scoring.py
      value_objects.py

    application/
      __init__.py
      ports/
        __init__.py
        package_repository.py
        package_registry.py
        queue.py
        unit_of_work.py
      use_cases/
        __init__.py
        enqueue_scan.py
        scan_package.py
        monitor_updates.py
        list_packages.py
        list_findings.py
        list_scan_results.py

    infrastructure/
      __init__.py
      db/
        __init__.py
        models.py
        session.py
        repositories.py
        unit_of_work.py
      npm/
        __init__.py
        registry_client.py
        tarball_downloader.py
      queue/
        __init__.py
        celery_app.py
        producer.py
      scanner/
        __init__.py
        extractor.py
        package_json_reader.py
        install_hook_detector.py
        binary_detector.py
        obfuscation_detector.py
        command_execution_detector.py
        size_comparator.py
      logging/
        __init__.py
        setup.py

    worker/
      __init__.py
      tasks.py

    scheduler/
      __init__.py
      main.py

    core/
      __init__.py
      config.py
      exceptions.py

  tests/
    unit/
    integration/
```

---

# Phase 0 — Project Documentation Setup

## User Story

As a developer building `npm-sentinel`, I want clear project documents before implementation starts, so that the AI agent and future contributors understand the engineering rules, implementation phases, scope, and definition of done.

## Scope

Create:

- `AGENTS.md`
- `PROJECT_PLAN.md`
- initial `README.md`

## Tasks

- Write `AGENTS.md` with architecture and code quality guardrails.
- Write `PROJECT_PLAN.md` with phases, user stories, tasks, and acceptance criteria.
- Create a minimal `README.md` with project goal, services, and run command placeholder.
- Add a short architecture statement.

## Acceptance Criteria

- `AGENTS.md` defines engineering rules and forbidden shortcuts.
- `PROJECT_PLAN.md` defines phased implementation work.
- `README.md` has the initial project overview.
- Tasks and guardrails are not mixed together.

## Definition of Done

Documentation exists and can guide code generation without ambiguity.

---

# Phase 1 — Runnable Project Skeleton

## User Story

As a backend engineer, I want a Dockerized project skeleton with FastAPI, PostgreSQL, RabbitMQ, Celery, and pytest, so that the system has a runnable foundation before scanner logic is added.

## Business Value

This proves that the assignment can run with one Docker Compose command and already has the required service shape: API, worker, scheduler, database, and queue.

## Scope

Implement the basic runtime structure only.

## Tasks

- Create `Dockerfile`.
- Create `docker-compose.yml` with:
  - `api`
  - `worker`
  - `scheduler`
  - `postgres`
  - `rabbitmq`
- Create `pyproject.toml`.
- Add application config using environment variables.
- Create FastAPI app entrypoint.
- Add `GET /health` endpoint.
- Add Celery app configuration using RabbitMQ as broker.
- Add PostgreSQL connection/session setup.
- Add initial pytest structure.
- Add `.env.example`.

## Async / Concurrency Guidance

- No scan concurrency is required in this phase.
- Celery worker only needs to start successfully.
- API should not perform background scanning yet.

## Acceptance Criteria

- `docker compose up --build` starts all services.
- `api` starts and exposes `GET /health`.
- `worker` starts and connects to RabbitMQ.
- `scheduler` starts, even if it only logs a placeholder message.
- PostgreSQL starts successfully.
- RabbitMQ starts successfully.
- `pytest` can run.

## Suggested Tests

- `GET /health` returns `200 OK`.
- Config object loads required environment variables.

## Definition of Done

The system boots through Docker Compose and has a working API health check.

---

# Phase 2 — Database Foundation and Concurrency-Safe Persistence

## User Story

As a backend engineer building `npm-sentinel`, I want to implement a PostgreSQL persistence layer with clear repository boundaries, uniqueness constraints, and idempotent write behavior, so that multiple Celery workers can safely persist package metadata, package versions, scan results, and findings without corrupting data when jobs are retried or processed concurrently.

## Business Context

The scanner uses RabbitMQ and Celery to process package scans asynchronously. Multiple worker processes may consume jobs from the same queue. Duplicate messages, retries, or parallel scans can happen, so the database must protect the system from duplicate or inconsistent records.

The database is the durable source of truth for:

- packages
- package versions
- latest and previous version metadata
- scan status
- findings
- risk score
- worker failures

## Scope

Implement persistence only. Do not implement actual package scanning yet.

## Tables

### `packages`

Fields:

- `id`
- `name`
- `latest_scanned_version`
- `last_scanned_at`
- `created_at`
- `updated_at`

Rules:

- `name` must be unique.
- inserting the same package twice must not create duplicates.
- concurrent inserts for the same package must be handled safely.

### `package_versions`

Fields:

- `id`
- `package_id`
- `version`
- `published_at`
- `tarball_url`
- `integrity`
- `unpacked_size`
- `file_count`
- `package_json` JSONB
- `dependencies` JSONB
- `scripts` JSONB
- `created_at`

Rules:

- `package_id + version` must be unique.
- latest and previous versions are both stored here.
- duplicate version inserts must be idempotent.

### `scan_results`

Fields:

- `id`
- `package_id`
- `latest_version`
- `previous_version`
- `status`
- `score`
- `risk_level`
- `error_message`
- `started_at`
- `finished_at`
- `created_at`

Rules:

- valid statuses: `queued`, `running`, `completed`, `failed`.
- `previous_version` may be null.
- `score` may be null until completed.
- failed scans must persist `error_message`.

### `findings`

Fields:

- `id`
- `scan_result_id`
- `finding_type`
- `severity`
- `category`
- `file_path`
- `description`
- `evidence`
- `created_at`

Rules:

- every finding belongs to a scan result.
- `file_path` may be null for metadata-level findings.
- `evidence` must be small and safe.
- do not store full suspicious files.

## Tasks

- Define SQLAlchemy models.
- Add database session factory.
- Add repository implementation.
- Add unit-of-work if useful.
- Add uniqueness constraints.
- Implement package upsert.
- Implement package version upsert.
- Implement scan result creation/update.
- Implement scan failure persistence.
- Implement finding persistence.
- Add repository tests.

## Async / Concurrency Guidance

- Phase 2 does not require async database code.
- Prefer synchronous SQLAlchemy sessions for assignment speed.
- Each API request or worker task should get its own DB session/unit of work.
- Do not share a global SQLAlchemy session across workers.
- Do not manually use threads for database writes.
- Idempotency and DB constraints are the concurrency solution in this phase.

## Acceptance Criteria

- PostgreSQL starts through Docker Compose.
- Application can connect to PostgreSQL.
- All core tables exist.
- Package name uniqueness is enforced.
- Package version uniqueness is enforced.
- Repository can upsert packages.
- Repository can upsert package versions.
- Repository can create and update scan results.
- Repository can save findings.
- Duplicate package inserts do not create duplicates.
- Duplicate package version inserts do not create duplicates.
- Failed scans can be persisted.
- Repository tests pass.

## Suggested Tests

- Package upsert is idempotent.
- Version upsert is idempotent.
- Scan result lifecycle works.
- Failed scan lifecycle works.
- Findings are linked to scan result.

## Definition of Done

The persistence layer is ready for concurrent Celery workers and repository tests pass.

---

# Phase 3 — Queue Foundation

## User Story

As a backend engineer, I want the API and scheduler to enqueue scan jobs into RabbitMQ and a Celery worker to consume them, so that package scanning is asynchronous, retry-friendly, and separated from HTTP request handling.

## Scope

Implement job production and job consumption without real scanning logic.

## Tasks

- Create Celery app configuration.
- Create scan task: `scan_package(package_name: str, reason: str = "manual")`.
- Create queue producer adapter.
- Create `EnqueueScanUseCase`.
- Add `POST /scans/{package_name}` endpoint.
- Add placeholder worker task that logs the job.
- Persist a queued/running scan result if appropriate.

## Async / Concurrency Guidance

- This phase introduces queue-level asynchronous processing.
- API must enqueue jobs and return immediately.
- Worker consumes jobs outside the API request lifecycle.
- Do not scan packages in the API process.
- Use Celery worker concurrency for parallel job processing later.
- Default worker concurrency target: `--concurrency=5`.

## Acceptance Criteria

- `POST /scans/lodash` returns a queued response.
- RabbitMQ receives the job.
- Worker consumes the job.
- Worker logs `scan_job_received` with package name and reason.
- API remains responsive while job is processed.
- Multiple workers can consume from the same queue without code changes.

## Suggested Tests

- API scan endpoint validates package name.
- API scan endpoint calls enqueue use case.
- Queue producer receives expected payload.

## Definition of Done

The API can enqueue scan jobs and the worker can consume them through RabbitMQ.

---

# Phase 4 — NPM Registry Client

## User Story

As a scanner worker, I want a clean NPM registry client, so that I can fetch package metadata, identify latest and previous versions, and extract metadata needed for persistence and comparison.

## Scope

Implement metadata fetching only. Do not download tarballs yet.

## Tasks

- Implement `NpmRegistryClient`.
- Fetch metadata from NPM registry.
- Parse latest version.
- Parse previous version.
- Extract version metadata:
  - package name
  - version
  - published date
  - dependencies
  - scripts
  - package JSON information
  - tarball URL
  - integrity
  - unpacked size
  - file count when available
- Handle package not found.
- Handle timeout.
- Handle malformed response.
- Add tests using fake registry JSON fixtures.

## Async / Concurrency Guidance

- NPM metadata fetching is network-bound and should use async HTTP.
- Use `httpx.AsyncClient`.
- Add request timeouts.
- Scheduler must use bounded concurrency when checking many packages.
- Do not use unbounded `asyncio.gather()` for the top 1000 packages.
- Use a semaphore, for example `asyncio.Semaphore(10)`.

## Acceptance Criteria

- Client can fetch metadata for a real package.
- Client can identify latest version.
- Client can identify one previous version.
- Client can extract package JSON fields.
- Client handles missing previous version gracefully.
- Unit tests pass with fixture data.

## Suggested Tests

- Latest version parser works.
- Previous version parser works.
- Metadata extractor returns dependencies and scripts.
- Missing package raises controlled exception.
- Missing previous version returns `None`.

## Definition of Done

The application can fetch and parse NPM package metadata without downloading package tarballs.

---

# Phase 5 — Tarball Download and Safe Extraction

## User Story

As a scanner worker, I want to download NPM tarballs into temporary directories and extract them safely, so that package contents can be statically analyzed without persisting raw files or exposing the system to unsafe archive paths.

## Scope

Implement download and extraction. Do not implement detectors yet.

## Tasks

- Implement `TarballDownloader`.
- Download tarballs using tarball URL from metadata.
- Stream downloads where practical.
- Add timeout and basic size guard where practical.
- Implement `SafeExtractor`.
- Validate archive member paths before extraction.
- Prevent path traversal.
- Avoid following symlinks outside extraction root.
- Use `TemporaryDirectory` during scan flow.
- Add tests for safe extraction.

## Async / Concurrency Guidance

- Tarball download is network-bound and should be async.
- Extraction is local disk/CPU work and should be synchronous.
- Do not extract archives in the FastAPI process.
- Do not manually create threads.
- Do not allow unbounded parallel downloads.

## Acceptance Criteria

- Tarball can be downloaded into a temp directory.
- Tarball can be extracted into a temp directory.
- Temporary files are deleted after the context exits.
- Path traversal archive entries are rejected.
- Extraction does not execute package code.

## Suggested Tests

- Valid tarball extracts successfully.
- Archive path traversal is rejected.
- Malformed tarball raises controlled exception.
- Temporary directory cleanup works.

## Definition of Done

Workers can safely download and extract package tarballs for static analysis.

---

# Phase 6 — Static Detectors

## User Story

As a scanner worker, I want small, focused static detectors, so that package contents and metadata can be analyzed for suspicious supply-chain indicators in a testable and explainable way.

## Scope

Implement required and bonus detectors as independent modules.

## Required Detectors

### Install Hook Detector

Detect lifecycle scripts:

- `preinstall`
- `install`
- `postinstall`

Optionally detect:

- `prepare`
- `prepublish`
- `prepublishOnly`

Finding types:

- `INSTALL_HOOK_ADDED`
- `INSTALL_HOOK_REMOVED`
- `INSTALL_HOOK_PRESENT`

### Size Comparator

Compare latest and previous version size.

Finding types:

- `SIZE_INCREASE_MEDIUM`
- `SIZE_INCREASE_HIGH`

Suggested thresholds:

- 30% to 100% increase: medium
- more than 100% increase: high

### Binary Detector

Detect executable binaries by magic bytes and extension.

Magic bytes:

- ELF: `7F 45 4C 46`
- PE/EXE/DLL: `4D 5A`

Extensions:

- `.exe`
- `.dll`
- `.so`
- `.dylib`
- `.node`

Finding type:

- `EXECUTABLE_BINARY`

## Bonus Detectors

### Obfuscation Detector

Patterns:

- `eval(`
- `Function(`
- `_0x[a-fA-F0-9]+`
- hex-encoded strings
- long base64-looking strings
- very long minified lines

Finding type:

- `OBFUSCATED_CODE`

### Command Execution Detector

Patterns:

- `child_process`
- `exec(`
- `execSync(`
- `spawn(`
- `spawnSync(`
- `curl`
- `wget`
- `powershell`
- `cmd.exe`
- `bash -c`
- `sh -c`

Finding type:

- `COMMAND_EXECUTION_PATTERN`

## Tasks

- Implement package JSON reader.
- Implement install hook detector.
- Implement size comparator.
- Implement binary detector.
- Implement obfuscation detector.
- Implement command execution detector.
- Create shared `Finding` domain object if not already created.
- Add unit tests for each detector.

## Async / Concurrency Guidance

- Static detectors should be synchronous.
- Do not make detector functions async.
- Do not use threads inside detectors for the assignment version.
- Detectors should not write to DB.
- Detectors should not enqueue jobs.
- Detectors should return findings only.

## Acceptance Criteria

- Each detector is independently unit tested.
- Each detector returns structured findings.
- Detectors do not have side effects.
- Detectors do not execute package code.
- File-level detectors handle unreadable/large files gracefully.

## Suggested Tests

- Install hook added is detected.
- Install hook removed is detected.
- Install hook present is detected.
- ELF magic byte is detected.
- PE magic byte is detected.
- Executable extension is detected.
- Obfuscation pattern is detected.
- Command execution pattern is detected.
- Size increase is categorized correctly.

## Definition of Done

All required detectors and bonus detectors are implemented with unit tests.

---

# Phase 7 — Scoring Engine

## User Story

As a security reviewer, I want every scan to produce an explainable risk score from 1 to 100, so that packages can be prioritized based on suspicious indicators.

## Scope

Implement deterministic scoring based on findings.

## Scoring Model

Base score:

```text
1
```

Suggested increments:

```text
+25 executable binary found
+20 new preinstall/install/postinstall hook added
+15 command execution pattern found
+15 obfuscation pattern found
+10 size increased by more than 100%
+5 size increased by 30–100%
+5 suspicious lifecycle script already present
+5 large dependency increase
```

Cap:

```python
score = min(score, 100)
```

Risk levels:

```text
1–30     low
31–70    medium
71–100   high
```

## Tasks

- Implement `calculate_score(findings)`.
- Implement `calculate_risk_level(score)`.
- Ensure score is traceable to findings.
- Add unit tests.

## Async / Concurrency Guidance

- Scoring is pure local logic.
- Keep it synchronous.
- Do not access DB from scoring.
- Do not enqueue jobs from scoring.

## Acceptance Criteria

- Score is between 1 and 100.
- Score is capped at 100.
- Risk level mapping is deterministic.
- Score can be explained by findings.
- Unit tests cover low, medium, high, and capped scores.

## Definition of Done

Every scan can produce a deterministic and explainable risk score.

---

# Phase 8 — Full Scan Use Case

## User Story

As a Celery worker, I want to execute a complete package scan from metadata fetch to persisted findings, so that each package can be analyzed, scored, and stored reliably.

## Scope

Connect metadata client, downloader, extractor, detectors, scoring, and repository into one application use case.

## Scan Flow

1. Receive package name and reason.
2. Create or update scan result as `running`.
3. Fetch NPM metadata.
4. Identify latest version.
5. Identify previous version.
6. Save package record.
7. Save latest version metadata.
8. Save previous version metadata if available.
9. Download latest tarball.
10. Download previous tarball if available.
11. Extract safely into temporary directories.
12. Read package JSON.
13. Run install hook detection.
14. Run size comparison.
15. Run binary detection.
16. Run obfuscation detection.
17. Run command execution detection.
18. Calculate score and risk level.
19. Save findings.
20. Mark scan completed.
21. Delete temporary files.

On failure:

1. Mark scan failed.
2. Save error message.
3. Log structured error.
4. Let the worker continue processing other jobs.

## Tasks

- Implement `ScanPackageUseCase`.
- Wire use case into Celery task.
- Add structured logs.
- Persist success and failure states.
- Ensure temporary files are always cleaned up.
- Add integration test with small fake package tarballs.

## Async / Concurrency Guidance

- The use case runs inside a Celery worker task.
- Celery/RabbitMQ provides job-level async processing.
- Use async metadata/download clients if already implemented.
- Keep extraction and detectors synchronous.
- Keep DB writes transactionally controlled.
- Do not manually create threads.
- Duplicate jobs must be safe because of DB idempotency.

## Acceptance Criteria

- Worker can scan a real package such as `lodash`.
- Latest and previous metadata are saved.
- Findings are saved.
- Score is saved.
- Raw package files are deleted.
- Failed scans are persisted.
- API can show the result after scan completion.

## Suggested Tests

- Fake package scan completes successfully.
- Fake package with install hook produces finding.
- Fake package with binary produces finding.
- Failed metadata fetch marks scan failed.
- Duplicate scan does not corrupt DB.

## Definition of Done

A queued package scan can be fully processed and persisted by the worker.

---

# Phase 9 — Scheduler / Continuous Update Monitor

## User Story

As the system, I want to continuously monitor the top NPM packages for new versions, so that updated packages are automatically queued for scanning and saved in the database.

## Scope

Implement scheduler/update monitor.

## Tasks

- Load top NPM package list.
- Support configurable package limit for local demo.
- Fetch metadata for packages.
- Compare latest version with database `latest_scanned_version`.
- Enqueue scan when package is new or updated.
- Add structured logs.
- Add scheduler interval config.

## Config

Recommended local demo settings:

```env
TOP_PACKAGE_LIMIT=20
SCHEDULER_INTERVAL_SECONDS=300
SCHEDULER_METADATA_CONCURRENCY=10
```

## Async / Concurrency Guidance

- Scheduler may fetch metadata concurrently.
- Concurrency must be bounded with a semaphore.
- Do not run multiple scheduler replicas in Docker Compose.
- Scheduler should enqueue jobs, not scan packages.
- Scheduler DB checks can remain synchronous for simplicity.

## Acceptance Criteria

- Scheduler starts as a Docker Compose service.
- Scheduler checks package metadata.
- Scheduler enqueues never-scanned packages.
- Scheduler enqueues updated packages.
- Scheduler does not enqueue unchanged packages repeatedly.
- Scheduler logs `update_detected` and `job_enqueued`.

## Suggested Tests

- New package is enqueued.
- Updated package is enqueued.
- Unchanged package is not enqueued.
- Metadata checks use bounded concurrency.

## Definition of Done

The system can continuously monitor NPM packages and enqueue scans for new or changed versions.

---

# Phase 10 — API Result Endpoints

## User Story

As a user of the scanner, I want API endpoints to trigger scans and inspect packages, scan results, and findings, so that I can review suspicious NPM packages without reading the database directly.

## Scope

Implement minimal useful API for demo and review.

## Endpoints

```http
GET /health
POST /scans/top-packages
POST /scans/{package_name}
GET /packages
GET /packages/{package_name}
GET /scan-results
GET /findings
```

Useful filters:

```http
GET /packages?risk_level=high
GET /scan-results?status=failed
GET /findings?severity=high
GET /findings?type=executable_binary
```

## Tasks

- Add list packages use case.
- Add package details use case.
- Add list scan results use case.
- Add list findings use case.
- Add pagination where practical.
- Add response schemas.
- Add API tests.

## Async / Concurrency Guidance

- API endpoints should be fast.
- API should only read DB or enqueue jobs.
- API must not download or scan packages.
- Long-running work belongs in Celery worker.

## Acceptance Criteria

- User can trigger a package scan.
- User can trigger top package scan enqueueing.
- User can list packages.
- User can view package details.
- User can list scan results.
- User can list findings.
- User can filter high-severity findings.

## Suggested Tests

- Health endpoint returns OK.
- Scan endpoint enqueues job.
- Package list endpoint returns persisted packages.
- Findings endpoint supports severity filter.

## Definition of Done

The system exposes enough API functionality to demo scanning and review results.

---

# Phase 11 — Testing Hardening

## User Story

As a reviewer, I want the project to include meaningful tests, so that I can trust the scanner logic, scoring, repository behavior, and API basics.

## Scope

Add unit and integration tests.

## Required Unit Tests

```text
test_scoring.py
test_install_hook_detector.py
test_binary_detector.py
test_obfuscation_detector.py
test_command_execution_detector.py
test_size_comparator.py
test_safe_extractor.py
```

## Required Integration Tests

```text
test_repository.py
test_scan_package_use_case.py
test_api_health.py
test_api_scan_enqueue.py
```

## Tasks

- Add test fixtures.
- Add fake package JSON examples.
- Add fake tarball fixtures if practical.
- Add repository integration tests.
- Add API tests.
- Add scan use case test with fake clients.
- Ensure tests run with one command.

## Async / Concurrency Guidance

- Async clients should be mocked or tested with async pytest where needed.
- Pure detectors should remain sync tests.
- Do not require RabbitMQ for all unit tests.
- Keep queue tests isolated with fake producer where practical.

## Acceptance Criteria

- Core detector tests pass.
- Scoring tests pass.
- Repository tests pass.
- API health and scan enqueue tests pass.
- Tests can run locally and in Docker.

## Definition of Done

The project has enough test coverage to demonstrate senior engineering discipline.

---

# Phase 12 — Logging, Evidence, and README Polish

## User Story

As a reviewer, I want clear logs, evidence files, and README documentation, so that I can quickly understand how the system works, how to run it, and what tradeoffs were made.

## Scope

Polish the project for submission.

## Logging Events

Add structured logs for:

```text
job_enqueued
scan_job_received
scan_started
metadata_fetch_started
metadata_fetch_completed
tarball_download_started
tarball_download_completed
tarball_extracted
finding_detected
scan_completed
scan_failed
scan_result_saved
update_detected
```

Recommended fields:

```text
package_name
latest_version
previous_version
job_reason
scan_result_id
score
risk_level
duration_ms
error_type
error_message
```

## Evidence Files

Create:

```text
evidence/
  sample_logs.txt
  sample_api_response.json
  sample_findings.json
  architecture_notes.md
```

Optional:

```text
evidence/screenshots/
```

## README Sections

```text
Goal
Architecture
Services
Data Flow
Detection Rules
Scoring Model
Database Schema
How to Run
API Endpoints
How to Run Tests
Production Considerations
Limitations
Evidence / Example Output
```

## Tasks

- Add structured logging.
- Add sample logs.
- Add sample API responses.
- Add final README.
- Document limitations.
- Document production considerations.
- Document why RabbitMQ is used.
- Document why workers are stateless.
- Document static-analysis-only safety.

## Acceptance Criteria

- README explains how to run the project.
- README explains architecture clearly.
- README explains scoring clearly.
- README explains limitations honestly.
- Evidence files exist.
- Logs are structured and useful.

## Definition of Done

The project is ready to zip and submit.

---

# Final Delivery Checklist

Before submission, verify:

```text
[ ] docker compose up --build starts all services
[ ] API health endpoint works
[ ] RabbitMQ starts
[ ] PostgreSQL starts
[ ] Worker starts and consumes jobs
[ ] Scheduler starts and enqueues jobs
[ ] Manual scan endpoint works
[ ] At least one real package can be scanned
[ ] Latest version metadata is stored
[ ] Previous version metadata is stored when available
[ ] Findings are stored
[ ] Score is stored
[ ] Failed scans are persisted
[ ] Temporary files are deleted
[ ] Tests pass
[ ] README is complete
[ ] Evidence files are included
[ ] No package code is executed
[ ] No raw package files are permanently stored
[ ] Project can be zipped for submission
```

---

# Suggested Implementation Order for AI/Codex

Use this exact order when asking an AI agent to implement the project:

1. Create skeleton and Docker Compose only.
2. Make the API health endpoint work.
3. Add database models and repositories.
4. Add Celery/RabbitMQ enqueue/consume flow.
5. Add NPM registry client.
6. Add tarball downloader and safe extractor.
7. Add static detectors with tests.
8. Add scoring with tests.
9. Connect full scan use case.
10. Add scheduler.
11. Add API result endpoints.
12. Add integration tests.
13. Polish logs, README, and evidence.

Do not ask the AI agent to generate the whole project at once. Each phase should be implemented, run, tested, and committed before moving to the next.

---

# Final Success Definition

The project is successful when it demonstrates a clean production-shaped backend system rather than a simple script:

- FastAPI modular monolith
- RabbitMQ/Celery asynchronous job processing
- PostgreSQL durable persistence
- stateless and horizontally scalable workers
- safe temporary package analysis
- latest vs previous version comparison
- required suspicious indicator detection
- bonus static analysis indicators
- deterministic scoring
- structured logging
- meaningful tests
- one-command Docker Compose run
- clear README and evidence
