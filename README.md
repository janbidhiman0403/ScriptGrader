# ScriptGrader

AI-based evaluation of handwritten answer sheets, with every mark traceable
to specific evidence on the page. No separate OCR stage — a vision-capable
LLM reads the handwriting and grades against a rubric in one pass, then
verifies its own work in a second pass before returning a result.

## Why this architecture

Most academic implementations of this idea (see `docs/comparable-repos.md`
for a survey) run OCR and grading as two disconnected stages: transcribe the
handwriting, then score the transcript. That throws away information — the
grading model never sees the original page, only someone else's guess at
what it says — and it produces scores with no evidence trail back to the
handwriting itself.

This project grades directly from the image instead, and forces the model's
output through a strict schema that requires evidence and a reason for
every single mark, so a teacher or student can always see exactly which
words earned or lost points.

## Architecture

```
Upload (image + question + model answer + rubric)
        |
        v
Preprocessing  — validate, orient, downscale, contrast-enhance
        |
        v
Grading engine — pass 1: draft transcription + per-criterion score
                 pass 2: model re-checks its own draft against the image
        |
        v
Schema validation — marks can't exceed max, totals must add up exactly,
                     every criterion must cite evidence (enforced by
                     pydantic validators, not just prompt instructions)
        |
        v
Structured JSON response -> rendered as a marking ledger in the UI
```

## Project layout

```
app/
  main.py              FastAPI app, startup, centralized error handling
  core/
    config.py          Settings, loaded from environment / .env
    exceptions.py      Domain-specific error types
    logging.py         Structured logging setup
  schemas/
    evaluation.py       Pydantic models with cross-field consistency
                        validators (totals must match, marks can't
                        exceed max, evidence can't be empty)
  services/
    preprocess.py       Image validation, EXIF-safe rotation, downscaling,
                        CLAHE contrast enhancement
    prompt.py           Grading + verification prompt templates
    engine.py           Two-pass grading call, retries, response parsing
  api/
    routes.py           HTTP endpoint, one job: orchestrate the above
static/
  index.html, styles.css, app.js    Frontend — no build step required
```

## Deploying with Docker

```bash
cp .env.example .env
# edit .env: set ANTHROPIC_API_KEY, TEACHER_API_KEY, POSTGRES_PASSWORD

docker compose up -d --build
```

This starts two containers: `app` (gunicorn running 4 uvicorn workers by
default, `WEB_CONCURRENCY` to tune) and `db` (Postgres 16). The app waits
for Postgres to report healthy before starting. Data persists in a named
volume (`db_data`) across restarts.

Put a reverse proxy (nginx, Caddy, or your cloud provider's load balancer)
in front of this for TLS — the app itself serves plain HTTP; terminating
HTTPS is deliberately left to the proxy layer rather than baked into the
container, since certificate management varies a lot by where you deploy.

**Honesty note:** the Dockerfile and compose file were verified for syntax
correctness, dependency resolution, and structural soundness (multi-stage
build, correct layer ordering, healthchecks configured), but this
environment has no Docker daemon, so an actual `docker compose up` has not
been run. Run it yourself and check `docker compose logs app` on first
boot before trusting it in production.

## Authentication

All grading and review endpoints require an `X-API-Key` header matching
`TEACHER_API_KEY`. This is single shared-secret auth — appropriate for a
small, trusted deployment (a school's own network, a small team), not
per-user accounts with individual audit trails. See `app/core/auth.py` for
the reasoning and what to replace this with if you need real multi-user
access control.

## Batch grading

`POST /api/grade/batch` accepts multiple `sheet_images` files against one
shared question/rubric. Each image is graded independently — one bad scan
returns an inline error for that item without failing the rest of the
batch. All successful items share a `batch_id`, filterable via
`GET /api/evaluations?batch_id=...`.

## Teacher review and override

Every graded evaluation is persisted. `PATCH /api/evaluations/{id}` lets a
teacher correct specific criteria's awarded marks; the total is always
recomputed server-side from the (possibly-overridden) criteria — a client
can never submit a total that doesn't match the sum. The original AI
output is preserved separately (`criteria_original` in the response) even
after an override, so there's an audit trail of what changed.

The frontend surfaces this: grade an answer, then use "Recent evaluations"
at the bottom of the page to reopen it and click "Override marks."

## Rate limiting

`RATE_LIMIT_GRADE` (default `10/minute`, slowapi syntax) caps grading
requests per client IP. Exists primarily as a cost guard — each grade
makes two model calls (draft + verify) — not just abuse prevention.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY

uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000` — the frontend is served directly by the
FastAPI app, no separate frontend server needed.

## Running without an API key (mock mode)

Set `MOCK_GRADING=true` in `.env` (leave `ANTHROPIC_API_KEY` blank) to run
the entire pipeline — upload, preprocessing, the API contract, and the
frontend's rendering — against a canned but realistic response, with no
network call and no cost. Useful for frontend development, demos, and CI.
**Never enable this in a real deployment** — it always returns the same
evaluation regardless of what was uploaded.

## Testing

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

54 tests covering: schema consistency validators (marks can't exceed max,
totals must match, evidence can't be empty), image preprocessing edge cases
(corrupt files, truncated uploads, oversized images, grayscale/RGBA
conversion), prompt construction, and every documented API status code
(200 happy path, 400, 413, 422, and stack-trace-leak prevention on 500s) —
run against the real FastAPI app in mock mode, not mocked-out unit stubs.

## Marked-sheet overlay

When the model returns a `bounding_box` for a criterion, the frontend draws
a color-coded highlight (green = full marks, gold = partial, red = zero)
directly over the uploaded image, synced with the ledger: hovering or
clicking a ledger row highlights its region on the image, and vice versa.
Bounding boxes are best-effort spatial grounding from the model, not
pixel-exact — treat them as an aid, not a guarantee.

## API

`POST /api/grade` — multipart form:

| Field | Type | Description |
|---|---|---|
| `sheet_image` | file | JPEG/PNG/WebP photo or scan of the handwritten answer |
| `question_number` | string | e.g. `"1a"` |
| `question_text` | string | The question as asked |
| `model_answer` | string | Key points the answer should cover |
| `rubric_json` | string | JSON array: `[{"name": str, "max_marks": number, "description": str}]` |

Returns an `EvaluationResult` (see `app/schemas/evaluation.py`) with a
per-criterion breakdown, each entry including `evidence` (what the student
wrote) and `reason` (why marks were given or withheld).

`GET /api/health` — liveness check.

Interactive API docs: `http://127.0.0.1:8000/docs`

## Error handling

Every failure mode returns a structured JSON error with an appropriate
status code — nothing crashes the process or leaks a stack trace:

| Status | Cause |
|---|---|
| 400 | Unreadable image, invalid rubric JSON |
| 413 | Upload exceeds `MAX_UPLOAD_MB` |
| 422 | Missing/malformed form fields (FastAPI validation) |
| 502 | Grading model unreachable, timed out, or returned unparseable output after retries |
| 500 | Anything unexpected — logged with a full traceback server-side, generic message client-side |

## What's not included yet

- Authentication / multi-user accounts
- Persistent storage (results aren't saved anywhere — add a database layer
  if you need history)
- Batch grading of a full class set in one request
- Teacher override / regrade workflow in the UI (the schema and backend
  already return everything needed to build this — see the architecture
  diagram's "teacher review layer")

These were left out deliberately to keep the core grading loop — the part
that's actually hard to get right — the focus of this scaffold.

## What's still genuinely unverified

Being direct about this rather than letting it hide:

**Grading quality against real handwriting.** Everything has been tested
against mock-mode responses and the real HTTP/schema layer, not a live
call to the actual Anthropic vision model — that requires a funded API
key, which this environment doesn't have. Before relying on this for real
grading:

1. Set `MOCK_GRADING=false` and a real `ANTHROPIC_API_KEY`, then grade a
   handful of real scanned answers and check the transcription accuracy,
   scoring judgment, and evidence quality by hand.
2. Watch for prompt-following failures a schema can't catch — e.g. the
   model being too lenient or too harsh in a way that's internally
   consistent (marks add up correctly) but substantively wrong. Only a
   human reviewer comparing against real handwriting will catch that.
3. Bounding-box coordinates from the model are a known weaker capability
   for most vision LLMs than text transcription — verify a sample by eye
   before trusting the overlay positions.

**An actual Docker build.** This sandbox has no Docker daemon. The
Dockerfile and docker-compose.yml were checked for YAML/structural
correctness and every dependency they install was verified installable
and importable elsewhere in this same environment — but `docker compose
up` itself has never been run. Run it and read the startup logs before
trusting it.

**Postgres in practice.** The app has only been exercised against SQLite
in this environment. `DATABASE_URL` is standard SQLAlchemy syntax and
`psycopg2-binary` is in requirements.txt, but the actual connection to a
running Postgres container is unverified here.

**The frontend rendered in a real browser.** As before — every DOM ID the
JS references was checked against the HTML programmatically, and the
exact JSON contract each new feature (history list, override form) sends
and expects was verified via TestClient, matching field-for-field what a
real browser's `fetch()` would receive. But no headless browser was
available in this sandbox to literally screenshot it.
