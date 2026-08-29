# D-22 — `services/api` installs its own lock, not the repository-wide one

**Status:** Decided, 2026-08-18 (P8).
**Affects:** `requirements-api.in`, `requirements-api.lock`, `services/api/requirements.txt`.
Reverses the "one venv serves either role" note that file currently carries. No code changes.
**Related:** [[D-21]] (the deployment this exists for), [[D-3]] (`pyarrow` stays dev-only — the
same instinct, applied earlier).

## Context

`services/api/requirements.txt` is a one-line shim reading `-r ../../requirements.lock`, with a
comment recording that it was "retired as an independent API-only manifest" so that a single
virtual environment could serve both the API and the pipeline worker. On a development machine
that is convenient and costs nothing.

`requirements.lock` is the compiled closure of `requirements.in`, which covers **both** roles.
Its API half is four packages — `fastapi`, `uvicorn[standard]`, `pydantic-settings`,
`psycopg2-binary`. Its worker half pulls `vnstock==4.0.4`, and vnstock's own closure pulls
`pandas`, `numpy`, `matplotlib`, `seaborn`, `wordcloud`, `pillow` and `openpyxl`.

`services/api` imports none of the worker half. Its entire import graph is
`app/{main,health,config,runtime_guards}.py`, `app/routes/`, and `app/db/`, and the only
third-party names in it are the four above.

Deployment is what turns this from tidy into wrong. A free-tier build installs the whole closure
on every push — matplotlib and its C extensions included — to run a service that never imports
them. It is slow, it consumes build minutes and disk, and every one of those packages is
attack surface and a source of resolution failures in a service that has no use for it.

## Alternatives

**(a) Keep the single lock.** One manifest, one venv, no divergence to maintain, and the
existing comment's rationale preserved. Rejected: the rationale was written for a local
development environment and does not survive contact with a metered build.

**(b) Split: an API-only `.in` compiled to an API-only lock.** Chosen.

**(c) A multi-stage Dockerfile that prunes after install.** Solves image size without splitting
the manifest, but not build time, and it introduces a Dockerfile into a repository that has none
and a runtime Render supplies natively. Rejected as more machinery for less benefit.

## Decision

`requirements-api.in` holds the four direct API dependencies — the same entries already grouped
under the `# --- API (services/api/app) ---` header in `requirements.in`, which is where the
split was implicitly documented all along. It compiles to `requirements-api.lock`, and
`services/api/requirements.txt` points there.

`requirements.in` / `requirements.lock` keep both halves and remain what the local development
venv installs. The two manifests therefore overlap by design, and the API's four entries exist
in both files.

**The duplication is the cost of this decision and is worth naming.** A version bumped in one
file and not the other is a real divergence with no check to catch it — this repository has no
CI. The mitigation is that `requirements-api.in` is four lines and is a strict subset: the
`# --- API ---` block in `requirements.in` and the whole of `requirements-api.in` must stay
identical, and that is a one-glance comparison rather than a diff of a compiled closure.

**Both locks are compiled in a disposable `python:3.13-slim` Linux container**, per the
instruction in `requirements.in`'s own header and the procedure P6.0 followed. A
Windows-resolved lock is not authoritative — it resolves different wheels for a Linux target —
and must not be committed.

`services/api/.python-version` is added for the same deployment reason: Render's root directory
for that service is `services/api`, so the repository-root `.python-version` is outside its
view.

## The comment this replaces

The retired note in `services/api/requirements.txt` also cited
`docs/deployment/PYTHON_RUNTIME.md` for the lock-regeneration procedure. **That file does not
exist** — it is one of the phantom paths `docs/00-project-status.md` §5 catalogues, and
`requirements.in` cites it twice more. The procedure it was supposed to carry is stated above
and in `requirements.in`'s header; the dangling citations are corrected rather than left
pointing at nothing.

## Verified

P8 Validation row 1: `requirements-api.lock` compiled in a `python:3.13-slim` container, and a
clean virtual environment created from it imports `app.main` successfully with no `vnstock`,
`matplotlib`, `pandas` or `numpy` present. Not attempted at the time of writing.
