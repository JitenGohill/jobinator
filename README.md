# Jobinator

Jobinator is a local-first job application assistant. Its dashboard keeps the
canonical profile that later screening and application packets use as their source
of truth, and captures immutable job snapshots from configured discovery sources.

Profile data is stored in a local SQLite database. Nothing in this version requires
an API key or network access after dependencies are installed.

## Prerequisites

- Python 3.10 or newer
- Node.js 20 or newer
- npm 10 or newer

## First-time setup

From the repository root:

```bash
cp .env.example .env

python3 -m venv backend/.venv
backend/.venv/bin/pip install -e 'backend[dev]'

cd frontend
npm install
cd ..
```

The default database is created at `data/jobinator.db`. Both it and `.env` are
excluded from version control.

## Run the local dashboard

Start the Python process in one terminal:

```bash
backend/.venv/bin/uvicorn jobinator.main:app --app-dir backend --reload
```

Start the React development process in another:

```bash
cd frontend
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). Vite forwards `/api` requests
to FastAPI on port 8000.

The profile editor supports:

- A base CV
- Projects and their evidence
- Skills with proficiency
- A preferred stack
- Education and work history
- Supporting links and search constraints
- Writing samples and reusable STAR stories

## Discover ATS roles

Configure one or more public ATS sources or directly reachable posting URLs in `.env`:

```dotenv
JOBINATOR_GREENHOUSE_BOARD_TOKEN=acme
JOBINATOR_GREENHOUSE_COMPANY=Acme Corp

JOBINATOR_LEVER_SITE=acme
JOBINATOR_LEVER_COMPANY=Acme Corp

JOBINATOR_ASHBY_BOARD=acme
JOBINATOR_ASHBY_COMPANY=Acme Corp

JOBINATOR_CAREER_PAGE_URLS=["https://careers.acme.example/jobs/software-engineer"]
JOBINATOR_WORKDAY_POSTING_URLS=["https://acme.wd5.myworkdayjobs.com/en-US/Acme_Careers/job/Chicago-IL/Software-Engineer_JR-123"]
```

The source identifier is the final segment in the source's hosted jobs URL:
`boards.greenhouse.io/<token>`, `jobs.lever.co/<site>`, or
`jobs.ashbyhq.com/<board>`.

Direct company career pages are supported when the fetched HTML contains a
schema.org `JobPosting` JSON-LD record. Direct Workday `/job/` URLs use Workday's
public JSON endpoint. Blocked, missing, or unrecognized pages produce source
diagnostics; Jobinator does not attempt browser automation.
Use **Ingest configured sources** in the dashboard, or run the same source-adapter
entry point independently:

```bash
backend/.venv/bin/jobinator-ingest
```

Each discovery creates a new immutable local snapshot containing the original ATS
posting and normalized role details. Equivalent snapshots are presented as one
opportunity with their contributing sources and the preferred official or ATS apply
route. The dashboard and command report results per source, so one changed or failed
upstream response does not prevent successful sources from completing. Repeated
ingestion and failed fetches never replace earlier snapshots.

Saved updates use profile versions so an older browser tab cannot silently overwrite
newer profile data.

## Verification

Run the backend checks:

```bash
backend/.venv/bin/pytest backend/tests
backend/.venv/bin/mypy backend/jobinator backend/tests
backend/.venv/bin/ruff check backend
```

Run the frontend checks:

```bash
cd frontend
npm test
npm run typecheck
npm run build
```

Tests use deterministic profile and ATS fixtures, temporary SQLite databases, and no
secrets or live network calls.
