"""pipelines.artifact.activate — flip which loaded run the dashboard serves (D-8).

Deliberately separate from ``pipelines.artifact.load``: loading is idempotent and safe to
re-run unattended; activation changes what a live reader sees, so it stays a distinct,
explicit act with a human behind it (D-8 — "load automatically, activate manually").

Clear-then-set, both inside one transaction: within the same ``with cursor()`` block, first
clear any currently-active row for the target's ``similarity_measure``, then set the target.
The partial unique index ``ux_model_runs_one_active`` is checked per-statement (not deferred),
so the sequence goes 1 -> 0 -> 1 active rows for that measure and is never transiently 2 —
clear-then-set is safe by ordering, not because anything was relaxed.

A ``dcor2`` target is refused **before** either statement runs, naming the reason
(``docs/04`` §5: dCor is a research measure, the dashboard stays on the primary method) rather
than surfacing ``model_runs_dcor_never_active``'s raw constraint-violation text.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

__all__ = ["ActivationError", "activate"]


class ActivationError(RuntimeError):
    """A named reason a run cannot be activated. Never a raw CHECK-violation message."""


def activate(artifact_id: str) -> None:
    from pipelines.common.db import cursor  # noqa: PLC0415

    with cursor() as cur:
        cur.execute(
            "SELECT id, similarity_measure FROM model_runs WHERE artifact_id = %s",
            (artifact_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise ActivationError(
                f"artifact_id {artifact_id!r} is not in model_runs — "
                f"run pipelines.artifact.load first"
            )
        run_id, measure = row
        if measure == "dcor2":
            raise ActivationError(
                f"artifact_id {artifact_id!r} uses similarity_measure='dcor2' — dCor is a "
                f"research measure (docs/01 §7); docs/04 §5 keeps the dashboard on "
                f"'pearson_rho2' only. This is what model_runs_dcor_never_active enforces; "
                f"refused here so the reason is named instead of a raw CHECK violation."
            )

        cur.execute(
            "UPDATE model_runs SET is_active = false "
            "WHERE similarity_measure = %s AND is_active = true",
            (measure,),
        )
        cur.execute("UPDATE model_runs SET is_active = true WHERE id = %s", (run_id,))


# ---------------------------------------------------------------------------
# Self-check — no database, the same fake-cursor pattern as artifact.load._selftest.
# ---------------------------------------------------------------------------


def _selftest() -> int:
    import contextlib

    passed = 0
    failed: list[str] = []

    def check(label: str, fn) -> None:  # noqa: ANN001
        nonlocal passed
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            failed.append(label)
            print(f"  FAIL  {label}\n          {type(exc).__name__}: {exc}")
        else:
            passed += 1
            print(f"  PASS  {label}")

    class _Cursor:
        def __init__(self, log: list[tuple[Any, Any]], answers: list[Any]) -> None:
            self.log = log
            self.answers = answers
            self._last: Any = None

        def execute(self, sql: Any, params: Any = None) -> None:
            self.log.append((sql, params))
            self._last = self.answers.pop(0) if self.answers else None

        def fetchone(self) -> Any:
            return self._last

        def __enter__(self) -> _Cursor:
            return self

        def __exit__(self, *exc: Any) -> bool:
            return False

    def fake_db(answers: list[Any]) -> list[tuple[Any, Any]]:
        log: list[tuple[Any, Any]] = []

        @contextlib.contextmanager
        def fake_cursor():
            yield _Cursor(log, answers)

        db_mod.cursor = fake_cursor
        return log

    import pipelines.common.db as db_mod

    real_cursor = db_mod.cursor

    def _unknown_artifact_named() -> None:
        fake_db([None])
        try:
            _assert_raises(lambda: activate("nope"), Exception, "unloaded artifact_id")
        finally:
            db_mod.cursor = real_cursor

    check("activating an artifact_id never loaded is refused by name", _unknown_artifact_named)

    def _dcor_refused_before_any_update() -> None:
        log = fake_db([(5, "dcor2")])
        try:
            _assert_raises(lambda: activate("some-dcor-id"), Exception, "dcor2 target")
            _assert(not any("UPDATE" in str(sql) for sql, _ in log),
                    f"an UPDATE ran despite the dcor2 refusal: {log}")
        finally:
            db_mod.cursor = real_cursor

    check("a dcor2 target is refused before either UPDATE runs", _dcor_refused_before_any_update)

    def _clear_then_set_order() -> None:
        log = fake_db([(9, "pearson_rho2"), None, None])
        try:
            activate("some-pearson-id")
            updates = [(sql, params) for sql, params in log if "UPDATE" in sql]
            _assert(len(updates) == 2, updates)
            clear_sql, clear_params = updates[0]
            set_sql, set_params = updates[1]
            _assert("is_active = false" in clear_sql and "similarity_measure = %s" in clear_sql,
                    clear_sql)
            _assert(clear_params == ("pearson_rho2",), clear_params)
            _assert("is_active = true" in set_sql and "id = %s" in set_sql, set_sql)
            _assert(set_params == (9,), set_params)
        finally:
            db_mod.cursor = real_cursor

    check("clear (by measure) runs strictly before set (by id)", _clear_then_set_order)

    print()
    if failed:
        print(f"artifact.activate selftest: {passed} passed, {len(failed)} FAILED")
        return 1
    print(f"artifact.activate selftest: {passed} passed, 0 failed")
    return 0


def _assert(cond: bool, what: object) -> None:
    if not cond:
        raise AssertionError(str(what))


def _assert_raises(fn, exc_type: type[BaseException], what: str) -> None:
    try:
        fn()
    except exc_type:
        return
    raise AssertionError(f"expected {exc_type.__name__} for {what}, nothing raised")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m pipelines.artifact.activate",
        description="Activate one loaded artifact (D-8, manual). --selftest needs no DB.",
    )
    parser.add_argument("artifact_id", nargs="?", default=None)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        return _selftest()

    if not args.artifact_id:
        parser.error("give an artifact_id, or pass --selftest")
        return 2

    try:
        activate(args.artifact_id)
    except ActivationError as exc:
        print(f"FAILED — {exc}", file=sys.stderr)
        return 1
    print(f"activated {args.artifact_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
