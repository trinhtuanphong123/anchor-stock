"""pipelines.storage — where bytes land.

The local train track and the dashboard track run the SAME fetch and compute code. They differ
only in destination, and this package is that difference, isolated behind two Protocols.

Import ``ports`` for the types and ``factory`` for an instance. Do not import ``pg`` or
``localfs`` directly from application code: that would drag ``psycopg2`` (or ``pyarrow``) into
modules that have no business needing either, and it is what keeps ``pipelines.returns.build``
importable on a machine with no database configured at all.
"""

from pipelines.storage.ports import (
    CONFLICT_KEY,
    ON_CONFLICT_KEEP,
    PARTITION_COL,
    RECORD_KEYS,
    BarSink,
    BarSource,
    Dataset,
)

__all__ = [
    "CONFLICT_KEY",
    "ON_CONFLICT_KEEP",
    "PARTITION_COL",
    "RECORD_KEYS",
    "BarSink",
    "BarSource",
    "Dataset",
]
