"""Atomic JSON cache writes for regen_v3 source modules.

Concurrency context: `regen_v3/batch_runner.py` runs subjects across a
multiprocessing pool. When two subjects share the same upstream cache
key (e.g. two members of the Walton family hitting the same foundation
EIN, or two siblings on the same FEC contributor name) two workers can
race on the cache file. A naive `path.write_text(...)` allows one writer
to truncate the file while another is reading or writing it, producing
a half-written / corrupt JSON payload.

Pattern: write to a sibling `<name>.tmp`, then `os.replace()` onto the
final path. `os.replace` is atomic on POSIX (and on Windows, where it
overwrites unlike `os.rename`). A reader observes either the old file
or the fully-written new file — never an in-progress truncation.

A canonical copy of this helper already lives in `regen_v3/search.py`
(used for the Brave query cache). This module is the shared version
imported by per-source caches that previously used `path.write_text(...)`.

The `sort_keys` argument matches the per-file JSON format decision —
search.py serializes with `sort_keys=True` so cache hits re-serialize
to a byte-identical payload, but the original source-module caches
were written with `sort_keys=False` and we preserve that to avoid
churning every existing cache file on next run.
"""
from __future__ import annotations

import itertools
import json
import os
import threading
from pathlib import Path
from typing import Any

# Per-process counter so two threads in one process can't collide either.
_tmp_counter = itertools.count()
_tmp_counter_lock = threading.Lock()


def _next_tmp_suffix() -> str:
    with _tmp_counter_lock:
        n = next(_tmp_counter)
    return f".pid{os.getpid()}.t{threading.get_ident()}.{n}.tmp"


def atomic_write_json(
    path: Path,
    payload: Any,
    *,
    indent: int = 2,
    sort_keys: bool = False,
) -> None:
    """Write `payload` as JSON to `path` atomically.

    Creates parent directories if needed, writes to a per-writer temp file,
    then `os.replace`s onto the final path. The temp filename embeds pid +
    thread id + a process-local counter so two concurrent writers (multi-
    proc + multi-threaded) cannot share a tmp path and clobber each other's
    in-progress bytes. The last `os.replace` wins; readers see either the
    old file or a fully-written new file, never a partial write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + _next_tmp_suffix())
    try:
        tmp.write_text(
            json.dumps(payload, indent=indent, sort_keys=sort_keys),
            encoding="utf-8",
        )
        os.replace(tmp, path)
    finally:
        # In the rare error path (e.g. disk full mid-replace), make sure we
        # don't leave a stray .pid*.tmp file lying around.
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
