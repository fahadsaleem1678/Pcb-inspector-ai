# Local API contract

Base URL: `http://127.0.0.1:8000`. Interactive schema: `/docs`; JSON schema: `/openapi.json`.
No authentication is implemented yet. Every request uses the configured local developer identity.
Do not publish this milestone. Arbitrary owner headers and image URLs are not accepted.

| Method and path | Behavior |
| --- | --- |
| `POST /api/v1/inspections/upload` | Multipart `file`; 202 with `inspection_id` UUID and `QUEUED` |
| `GET /api/v1/inspections?limit=20&offset=0` | Newest-first local history; limit 1–100; nonnegative offset |
| `GET /api/v1/inspections/{id}` | State, dimensions, attempts, timestamps, model/result and failure code |
| `GET /api/v1/inspections/{id}/results` | Completed versioned report; 409 while pending or failed |
| `GET /api/v1/inspections/{id}/report` | Same report with JSON attachment headers |
| `GET /api/v1/inspections/{id}/image` | Sanitized, orientation-normalized PNG in report coordinate space |
| `GET /health` | Process liveness and explicit demo flag |
| `GET /ready` | Schema query and storage write/read/delete probe; 503 on failure |
| `GET /metrics` | Prometheus API count/latency metrics using route templates |

Missing/not-owned inspection: 404; invalid UUID or image: 422; oversized image/request: 413;
unexpected service failure: generic 500 with request ID. Results use explicit `is_demo` and
`model_version` metadata. UUIDs replace illustrative `INS-92831` identifiers in the scope.

Uploads accept JPEG and PNG by decoded content (MIME/filename are untrusted). Default bounds:
10 MiB compressed input, minimum 64 px per side, maximum 8192 px per side, 20 million pixels.
Animated images are rejected. The multipart envelope has a bounded 64 KiB allowance.
Source EXIF/text metadata is removed; orientation is applied before reporting dimensions.
The normalized PNG may be larger than the upload; decoded dimensions bound this conversion.

Polling is sufficient for M1/M2. Use approximately one-second intervals with backoff on errors and
stop at `COMPLETED` or `FAILED`. `COMPLETED` describes processing, not defect acceptance.
`NOT_EVALUATED` means no trained detector ran. Do not show a pass indicator for demo reports.

Readiness checks API dependencies, not worker availability. Worker heartbeat/queue-age
monitoring, inference metrics, quotas/rate limits, deployment CORS and authenticated URLs are
tracked in later milestones. No annotated asset exists until real detections are integrated.
