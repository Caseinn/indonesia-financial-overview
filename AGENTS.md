# AGENTS.md

Financial data pipeline: official sources → Bronze (raw artifacts in R2) → Silver (Parquet) → Gold (Parquet) → static JSON snapshot (public R2) → web dashboard (Vercel). Python 3.12 managed by uv, Pandas, PyArrow, orchestrated by GitHub Actions.

### Principles

- **KISS**: simplest thing that works; no speculative abstraction.
- **YAGNI**: build what the current milestone needs, not what a future one might.
- **DRY**: one source of truth (`config/indicators.yml`, `pipeline/models.py`, `pipeline/parsing.py`); extract duplication only when it repeats for the same reason.
- **SOLID**: each adapter and stage has one job; code depends on the shared contracts (envelope, `Observation`) and config, never on another concrete adapter.

### Commands

- Install uv: `pip install uv` (or the [standalone installer](https://docs.astral.sh/uv/getting-started/installation/)).
- Setup: `uv sync` creates `.venv` from `pyproject.toml` + `uv.lock`.
- Add a dependency: `uv add <package>` (never edit `requirements.txt`; the lockfile is the source of truth and must be committed).
- Run anything in the project env with `uv run`: `uv run python -m pipeline.run_monthly`, `uv run pytest`, `uv run ruff check .` then `uv run ruff format .`.

### Commit

- Use a conventional-commit prefix: `feat`, `fix`, `chore`, `refactor`, `docs`, `style`, `test`, `build`, `perf`.
- Keep each commit focused on **one chunk/change**. Separate unrelated changes into different commits.
- Subject: short message, **3–6 words** (e.g. `fix: seki parser fallback`).
- Subject line only — no commit body.
- Do not combine multiple chunks into a single commit unless they are tightly related.

### File Naming

- Python modules and packages: **snake_case** (`bi_seki.py`, `run_monthly.py`) — required by import semantics.
- SQL and YAML files: **snake_case** (`macro_observations.sql`, `indicators.yml`), matching the object they define.
- Docs and notebooks: **kebab-case** (`data-lineage.md`).
- Tests mirror the module they test: `tests/sources/test_bi_seki.py` for `pipeline/sources/bi_seki.py`.

### Code

- Entrypoints are thin: `pipeline/run_monthly.py` composes stages (bronze → silver → gold → quality), no business logic inline.
- Source adapters live in `pipeline/sources/`, one module per source. Each adapter is independently runnable and must fail alone: an OJK parse error must not erase a successful BI ingestion.
- Shared structures (`IngestionEnvelope`, `Observation`, result types) are dataclasses in `pipeline/models.py`. Adapters never invent ad-hoc dicts for these shapes.
- Indicator codes, units, frequencies, and normalization rules come from `config/indicators.yml`, never hardcoded strings in adapter code.
- Reusable parsing helpers (date parsing, numeric cleaning with Indonesian locale formats, checksum hashing) live in `pipeline/parsing.py`, not copy-pasted between adapters.
- Type hints on all public functions and dataclasses. `ruff check` must pass clean.
- Add **minimal docstrings** (`""" ... """`) to public modules, functions, classes, and dataclasses: one or two sentences saying _what_ it does and _why_ it has that shape (e.g. the business key excludes `source_file_sha256` because the checksum is lineage, not identity). Keep it short and plain: no emoji, no history chatter, no per-parameter essays unless a parameter is non-obvious.
- **No inline comments**: no `#` line notes or trailing `#` remarks. If something needs explaining, it gets a docstring; otherwise leave the code unannotated.
- No `print()`; use the `logging` module. Never log secrets or connection strings.
- Secrets only via environment variables (`.env` locally, GitHub secrets in CI). `.env.example` lists every required variable with placeholder values.

### Data Rules

- **Measured zero vs nothing to measure.** A missing period is `skipped`/`pending`, never a zero row. A `0` value only exists where the source published one. Quality checks report "source has not published" differently from "value is zero".
- Idempotency: rerunning with the same `source_file_sha256` must not duplicate Bronze objects or Silver rows. Bronze writes are write-once; Silver revisions flip `is_current` on the old row before inserting the new one.
- Parsers validate structure (headers, indicator labels, sheet shape) against expectations and **fail loudly** on drift — never silently import misaligned columns.
- **Never trust file extensions.** Route every source-file load through the magic-byte sniffer in `pipeline/parsing.py` (`D0 CF 11 E0` → xlrd, `50 4B 03 04` → openpyxl, HTML/XML fallback): government portals serve `.xlsx`, SpreadsheetML, or HTML disguised as `.xls`.
- Source requests are paced and retried: reuse sessions, keep a delay between calls, and back off on throttling. BI's WAF drops request bursts outright (verified: failures clear after roughly 20 s of quiet).
- Gold is rebuilt from Silver on every run after quality gates pass, written as Parquet under `gold/` in R2, and exported as a static JSON snapshot; there is no hosted database, so every run records its outcome as JSON under `ops/runs` in R2.
- Gold Parquet under `gold/` is a derived, disposable copy for inspection. Never read it back as a pipeline input; rebuild from Silver instead.
- Never auto-delete or overwrite implausible values — flag them for review; real economic shocks exist.

### Tests

- `pytest`, no network in unit tests; adapters are tested against committed fixtures in `tests/fixtures/` (real downloaded samples, trimmed).
- Every parser change that touches mapping updates the fixture and its expected output in the same commit.
- Quality checks get their own tests: a fixture with a known defect must fail the specific check, not crash the pipeline.
