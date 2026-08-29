"""pipelines.storage.factory — pick a backend without importing both.

``make_sink()`` / ``make_source()`` are the only place application code names a backend. The
backend module is imported *inside* the call, so a local-track run never imports ``psycopg2``
and a database run never imports ``pyarrow``.

The default is **local**. That matches where the project is: the model is trained offline and
Supabase holds nothing yet, so a command that just works against ``data/`` is the useful
default and ``--storage pg`` is the deliberate act. It also means no command fails with a
missing ``DATABASE_URL`` before there is a database to point at.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, get_args

from pipelines.storage.ports import BarSink, BarSource

__all__ = ["STORAGE_ENV_VAR", "StorageKind", "make_sink", "make_source", "resolve_kind"]

StorageKind = Literal["local", "pg"]

STORAGE_ENV_VAR = "DATN_STORAGE"
DEFAULT_KIND: StorageKind = "local"


def resolve_kind(kind: str | None = None) -> StorageKind:
    """Resolve the backend: explicit argument, then ``$DATN_STORAGE``, then ``local``.

    Read on every call rather than cached at import, so a test or a CLI can set the variable
    after this module is imported and still be obeyed.
    """
    raw = (kind or os.environ.get(STORAGE_ENV_VAR) or DEFAULT_KIND).strip().lower()
    valid = get_args(StorageKind)
    if raw not in valid:
        raise ValueError(
            f"unknown storage backend {raw!r}; expected one of {list(valid)} "
            f"(set {STORAGE_ENV_VAR} or pass --storage)"
        )
    return raw  # type: ignore[return-value]


def make_sink(kind: str | None = None, *, root: Path | None = None) -> BarSink:
    """Build a :class:`~pipelines.storage.ports.BarSink`. ``root`` applies to the local backend."""
    resolved = resolve_kind(kind)
    if resolved == "local":
        from pipelines.storage.localfs import LocalSink  # noqa: PLC0415

        return LocalSink(root=root)
    from pipelines.storage.pg import PostgresSink  # noqa: PLC0415

    return PostgresSink()


def make_source(kind: str | None = None, *, root: Path | None = None) -> BarSource:
    """Build a :class:`~pipelines.storage.ports.BarSource`."""
    resolved = resolve_kind(kind)
    if resolved == "local":
        from pipelines.storage.localfs import LocalSource  # noqa: PLC0415

        return LocalSource(root=root)
    from pipelines.storage.pg import PostgresSource  # noqa: PLC0415

    return PostgresSource()
