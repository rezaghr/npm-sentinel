# Architecture Notes

`npm-sentinel` is a FastAPI modular monolith with separate runtime processes:

- `api`: validates input, enqueues scan jobs, and serves read APIs.
- `worker`: consumes queue jobs and runs the scan pipeline.
- `scheduler`: periodically checks package metadata and enqueues updated packages.
- `postgres`: durable source of truth for package intelligence.
- `rabbitmq`: durable message broker for asynchronous job delivery.

Core API docs are exposed by FastAPI:

- Swagger UI: `/docs`
- ReDoc: `/redoc`
- OpenAPI JSON: `/openapi.json`

## Why RabbitMQ/Celery

- Keeps HTTP requests fast by moving scan work out of API request/response.
- Handles retries and back-pressure better than ad-hoc background tasks.
- Allows horizontal worker scaling without changing application logic.
- Preserves pending jobs durably when services restart.

## Why Workers Are Stateless

- Scan state and results are stored in PostgreSQL, not process memory.
- Pending work lives in RabbitMQ, not local queues.
- Temporary scan files are created only for a single scan and deleted afterward.
- Any worker instance can safely process any job, enabling scale-out and restart safety.

## Data Flow

1. API or scheduler decides a package should be scanned.
2. A `queue_jobs` row is persisted as `queued`, then a scan task is published to RabbitMQ.
3. A worker consumes the job, marks queue job `running`, and creates a running scan record.
4. Worker fetches latest/previous package metadata from npm registry.
5. Worker downloads and safely extracts tarballs into temporary directories.
6. Static detectors generate findings and scoring computes risk.
7. Findings and scan result are persisted in PostgreSQL.
8. Queue job is marked `completed` or `failed`.
9. API endpoints expose package, scan, and finding data for review.

## Static-Analysis Safety

- Package code is never executed.
- Archive extraction validates paths and rejects traversal/special files.
- Download and extraction have strict byte/member/depth limits.
- Scanner traversal has file-count and text-size limits.
- Evidence saved in DB is bounded text, not full raw package artifacts.

## Reliability Notes

- Duplicate queue deliveries are safe: each delivery creates an independent scan attempt.
- Failure states are persisted with error messages.
- Completed scan attempts are not overwritten by late failures from stale retries.
- Queue lifecycle is queryable via durable `queue_jobs` rows keyed by task id.
