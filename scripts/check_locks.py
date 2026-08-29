"""Verify each dependency manifest against its compiled lock.

**Why this exists.** ``requirements.in`` used to restate the API's four packages verbatim from
``requirements-api.in``, under a comment that admitted the arrangement outright: *"nothing checks
the agreement — there is no CI"*. The restatement is gone (``requirements.in`` now includes the
other file by reference) and the CI exists, so this is the check that closes the sentence.

What it asserts, for each ``.in``/``.lock`` pair:

1. every direct requirement appears in the lock, and
2. the version the lock pins actually satisfies the specifier the manifest asked for.

It does **not** re-resolve the dependency graph — that needs the pinned pip-tools compiler in the
disposable Linux container described in ``requirements.lock``'s own header, which is a different
job with different requirements. This catches the failure that arrangement was exposed to: a
manifest edited without the lock being regenerated.

Run as ``python -m scripts.check_locks`` or ``python scripts/check_locks.py``. No third-party
import, so it runs in any of the three environments CI builds.

**A specifier this cannot parse is a failure, never a pass.** The version comparison below
understands plain numeric releases (``2``, ``0.111``, ``4.0.4``), which is every form these
manifests use. Anything else — an epoch, a pre-release, a wildcard, ``~=`` — raises. A checker
that silently skips what it does not understand reports success it did not establish.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Each manifest and the lock it is compiled into.
PAIRS = (
    ("requirements.in", "requirements.lock"),
    ("requirements-api.in", "requirements-api.lock"),
)

_NAME = r"[A-Za-z0-9][A-Za-z0-9._-]*"
_REQUIREMENT = re.compile(
    rf"^(?P<name>{_NAME})"
    r"(?:\[(?P<extras>[^\]]*)\])?"
    r"(?P<spec>.*)$"
)
_RELEASE = re.compile(r"^\d+(?:\.\d+)*$")


class CheckError(Exception):
    """A manifest and its lock disagree, or a line could not be understood."""


def normalize(name: str) -> str:
    """PEP 503 normalization, so ``psycopg2-binary`` and ``psycopg2_binary`` are one package."""
    return re.sub(r"[-_.]+", "-", name).lower()


def release(version: str) -> tuple[int, ...]:
    """Parse a plain numeric release into a comparable tuple, or refuse it.

    Deliberately narrow. See the module docstring: refusing an unfamiliar form is the only way
    the result of this script means anything.
    """
    if not _RELEASE.match(version):
        raise CheckError(f"cannot compare version {version!r} — not a plain numeric release")
    return tuple(int(part) for part in version.split("."))


def satisfies(version: str, spec: str) -> bool:
    """True when ``version`` satisfies every clause of a comma-separated specifier."""
    if not spec.strip():
        return True
    left = release(version)
    for clause in spec.split(","):
        clause = clause.strip()
        match = re.match(r"^(==|>=|<=|!=|>|<)\s*(.+)$", clause)
        if not match:
            raise CheckError(f"cannot parse specifier clause {clause!r}")
        op, raw = match.group(1), match.group(2).strip()
        # A trailing ".*" or a pre-release suffix would compare wrongly rather than not at all,
        # which is the dangerous direction; release() refuses both.
        right = release(raw)
        ok = {
            "==": left == right,
            "!=": left != right,
            ">=": left >= right,
            "<=": left <= right,
            ">": left > right,
            "<": left < right,
        }[op]
        if not ok:
            return False
    return True


def strip_comment(line: str) -> str:
    """Drop a trailing ``#`` comment and surrounding whitespace."""
    return line.split("#", 1)[0].strip()


def read_manifest(path: Path, seen: set[Path] | None = None) -> dict[str, str]:
    """Return ``{normalized name: specifier}`` for a ``.in`` file, following ``-r`` includes."""
    seen = seen if seen is not None else set()
    resolved = path.resolve()
    if resolved in seen:
        raise CheckError(f"circular include reached {path.name}")
    seen.add(resolved)

    direct: dict[str, str] = {}
    for raw in resolved.read_text(encoding="utf-8").splitlines():
        line = strip_comment(raw)
        if not line:
            continue
        if line.startswith(("-r ", "--requirement ")):
            include = resolved.parent / line.split(None, 1)[1].strip()
            for name, spec in read_manifest(include, seen).items():
                direct[name] = spec
            continue
        if line.startswith("-"):
            continue  # an option line (-c, --index-url); not a requirement
        match = _REQUIREMENT.match(line)
        if not match:
            raise CheckError(f"{path.name}: cannot parse requirement {line!r}")
        direct[normalize(match.group("name"))] = match.group("spec").strip()
    return direct


def read_lock(path: Path) -> dict[str, str]:
    """Return ``{normalized name: pinned version}`` for a compiled lock."""
    pinned: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw[:1].isspace():
            continue  # the "# via ..." provenance block under each pin
        line = strip_comment(raw)
        if not line or line.startswith("-"):
            continue
        if "==" not in line:
            raise CheckError(f"{path.name}: lock line is not pinned with == : {line!r}")
        name, _, version = line.partition("==")
        name = name.split("[", 1)[0]
        pinned[normalize(name)] = version.strip()
    return pinned


def check_pair(manifest_name: str, lock_name: str) -> list[str]:
    """Return a list of human-readable problems; empty means the pair agrees."""
    manifest = REPO_ROOT / manifest_name
    lock = REPO_ROOT / lock_name
    problems: list[str] = []

    direct = read_manifest(manifest)
    pinned = read_lock(lock)
    if not direct:
        problems.append(f"{manifest_name}: no requirements found")
    if not pinned:
        problems.append(f"{lock_name}: no pins found")

    for name, spec in sorted(direct.items()):
        if name not in pinned:
            problems.append(f"{name}: required by {manifest_name}, absent from {lock_name}")
            continue
        version = pinned[name]
        if not satisfies(version, spec):
            problems.append(
                f"{name}: {lock_name} pins {version}, which does not satisfy "
                f"{spec!r} from {manifest_name}"
            )
    return problems


def main() -> int:
    problems: list[str] = []
    for manifest_name, lock_name in PAIRS:
        pair_problems = check_pair(manifest_name, lock_name)
        status = "OK" if not pair_problems else "FAILED"
        print(f"[{status}] {manifest_name} -> {lock_name}")
        problems.extend(pair_problems)

    # The API lock is compiled under `--constraint requirements.lock`, so it is meant to be a
    # strict subset agreeing version for version. Checking it here is nearly free and catches a
    # regeneration that used the constraint flag the D-22 record calls "NOT optional".
    root = read_lock(REPO_ROOT / "requirements.lock")
    api = read_lock(REPO_ROOT / "requirements-api.lock")
    disagreements = [
        f"{name}: requirements.lock pins {root[name]}, requirements-api.lock pins {version}"
        for name, version in sorted(api.items())
        if name in root and root[name] != version
    ]
    print(f"[{'OK' if not disagreements else 'FAILED'}] the two locks agree version for version")
    problems.extend(disagreements)

    if problems:
        print("\nProblems:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("\nAll manifests agree with their locks.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except CheckError as error:
        print(f"check_locks: {error}")
        sys.exit(2)
