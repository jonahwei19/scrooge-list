"""regen_v3 batch_runner — parallel cohort runner with checkpoint/resume.

Wraps `regen_v3.cli.run_one()` in a multiprocessing.Pool with per-subject
log redirection and an atomic JSON checkpoint so 10-subject batches can be
paused/resumed safely.

Hard cap: 10 subjects per invocation (override with --unsafe-allow-large).

Usage:
    python3 -m regen_v3.batch_runner --subjects daniel_loeb robert_kraft
    python3 -m regen_v3.batch_runner --from-file ./tier_b_seeds.txt --workers 4
    python3 -m regen_v3.batch_runner --resume <batch_id>
    python3 -m regen_v3.batch_runner --all --unsafe-allow-large --workers 4
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STATE_DIR = HERE / "cache" / "batch_state"
LOG_DIR = HERE / "cache" / "batch_logs"
STATE_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

HARD_CAP = 10


def _now_batch_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _state_path(batch_id: str) -> Path:
    return STATE_DIR / f"{batch_id}.json"


def _atomic_write_json(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
    os.replace(tmp, path)


def _load_state(batch_id: str) -> dict:
    fp = _state_path(batch_id)
    if not fp.exists():
        return {"batch_id": batch_id, "subjects": {}, "started": _now_batch_id()}
    return json.loads(fp.read_text())


def _save_state(state: dict) -> None:
    state["updated"] = _now_batch_id()
    _atomic_write_json(_state_path(state["batch_id"]), state)


def _pool_init(extract_counter, extract_lock, brave_ts, brave_lock) -> None:
    """Pool initializer (module-level for `spawn` picklability). Each worker
    calls this once at startup; installs the shared mp.Value handles into
    extract.py and search.py so the cost cap and Brave rate-limiter are
    enforced ACROSS workers, not per-worker."""
    from regen_v3 import extract as _extract_mod
    from regen_v3 import search as _search_mod
    _extract_mod.install_shared_counter(extract_counter, extract_lock)
    _search_mod.install_shared_rate_limiter(brave_ts, brave_lock)


def _worker(args: tuple) -> dict:
    """Pool worker: run one subject with stdout/stderr piped to a log file.

    Returns a status dict the parent merges into the checkpoint.
    """
    subject_id, opts = args
    log_fp = LOG_DIR / f"{subject_id}.log"
    t0 = time.time()
    status = "error"
    summary: dict = {}
    err: str | None = None

    # Redirect stdout/stderr to per-subject log so parallel runs don't interleave.
    log_fh = open(log_fp, "a", buffering=1)
    log_fh.write(f"\n===== {subject_id} @ {datetime.now(timezone.utc).isoformat()} =====\n")
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = log_fh, log_fh
    try:
        # Import inside worker so each process pays the import cost once and
        # avoids fork-related global-state surprises.
        from regen_v3.cli import run_one
        summary = run_one(
            subject_id,
            refresh=opts["refresh"],
            candidates_only=opts["candidates_only"],
            dry_run=opts["dry_run"],
            verbose=opts["verbose"],
            use_timestamp_run_id=False,
        )
        if summary.get("merged"):
            status = "merged"
        elif opts["candidates_only"] or opts["dry_run"]:
            status = "skipped"
        elif summary.get("validate_errors", 0):
            status = "error"
            err = f"validate_errors={summary['validate_errors']}"
        else:
            status = "skipped"
    except FileNotFoundError as e:
        err = f"FileNotFoundError: {e}"
    except KeyboardInterrupt:
        # Let Ctrl-C propagate so the parent pool can tear down cleanly.
        raise
    except BaseException as e:
        # Catch BaseException (not just Exception) so SystemExit / pydantic
        # ValidationError / SDK-internal exceptions can't escape and force
        # multiprocessing.Pool to try pickling a live exception object —
        # which historically hung the parent on the result queue.
        err = f"{type(e).__name__}: {e}"
        try:
            traceback.print_exc()
        except Exception:
            pass
    finally:
        sys.stdout, sys.stderr = old_out, old_err
        log_fh.close()

    return {
        "subject_id": subject_id,
        "status": status,
        "elapsed_sec": round(time.time() - t0, 1),
        "summary": summary,
        "error": err,
        "log": str(log_fp),
        "finished": datetime.now(timezone.utc).isoformat(),
    }


def _read_subjects_file(path: Path) -> list[str]:
    out = []
    for line in path.read_text().splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            out.append(s)
    return out


def _read_max_extract_calls() -> int:
    """Best-effort read of regen_v3.extract._live_call_count from a sentinel
    file the worker pool can't share. Workers are separate procs, so we
    aggregate via the per-subject summary if extract exposed it; otherwise
    return -1 (unknown)."""
    try:
        from regen_v3 import extract as ex
        return getattr(ex, "_live_call_count", -1)
    except Exception:
        return -1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--subjects", nargs="+", help="Explicit subject ids")
    g.add_argument("--from-file", type=Path, help="File with one subject id per line")
    g.add_argument("--all", action="store_true", help="All subjects in data/")
    g.add_argument("--resume", metavar="BATCH_ID",
                   help="Resume a prior batch; skips subjects already 'merged'")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--batch-id", help="Override batch id (default: ISO datetime)")
    ap.add_argument("--unsafe-allow-large", action="store_true",
                    help=f"Bypass {HARD_CAP}-subject hard cap")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--candidates-only", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args(argv)

    # Resolve subject list + batch state.
    if args.resume:
        batch_id = args.resume
        state = _load_state(batch_id)
        if not state["subjects"]:
            print(f"[resume] no state for batch {batch_id}", file=sys.stderr)
            return 2
        all_subjects = sorted(state["subjects"].keys())
        pending = [s for s in all_subjects
                   if state["subjects"].get(s, {}).get("status") != "merged"]
        print(f"[resume] {batch_id}: {len(pending)}/{len(all_subjects)} pending")
        subjects = pending
    else:
        if args.all:
            from regen_v3.cli import list_all_subjects
            subjects = list_all_subjects()
        elif args.from_file:
            subjects = _read_subjects_file(args.from_file)
        else:
            subjects = list(args.subjects)
        batch_id = args.batch_id or _now_batch_id()
        state = _load_state(batch_id)

    if not subjects:
        print("[batch] nothing to do")
        return 0

    if len(subjects) > HARD_CAP and not args.unsafe_allow_large:
        print(
            f"[batch] refusing: {len(subjects)} subjects > hard cap {HARD_CAP}. "
            "Pass --unsafe-allow-large to override.",
            file=sys.stderr,
        )
        return 2

    # Seed checkpoint with anything not already present.
    for sid in subjects:
        state["subjects"].setdefault(sid, {"status": "pending"})
    _save_state(state)

    opts = {
        "refresh": args.refresh,
        "candidates_only": args.candidates_only,
        "dry_run": args.dry_run,
        "verbose": args.verbose,
    }
    work = [(sid, opts) for sid in subjects]
    workers = max(1, min(args.workers, len(work)))
    print(f"[batch] {batch_id}: {len(work)} subjects, {workers} workers")
    print(f"[batch] state: {_state_path(batch_id)}")
    print(f"[batch] logs:  {LOG_DIR}/<subject>.log")

    counts = {"merged": 0, "skipped": 0, "error": 0}
    t0 = time.time()
    # `spawn` is safer than `fork` for processes that may have already imported
    # heavy native libs (anthropic, requests). Pay a small startup cost; gain
    # predictability.
    ctx = mp.get_context("spawn")
    # Shared cross-worker state: ONE LLM-extract counter + ONE Brave
    # rate-limit timestamp shared across all workers so the cap and the
    # 1-req/sec limit aren't multiplied by N workers (codex round 7 fix).
    shared_extract_count = ctx.Value("i", 0)
    shared_extract_lock = ctx.Lock()
    shared_brave_ts = ctx.Value("d", 0.0)
    shared_brave_lock = ctx.Lock()

    try:
        with ctx.Pool(
            processes=workers,
            initializer=_pool_init,
            initargs=(shared_extract_count, shared_extract_lock,
                      shared_brave_ts, shared_brave_lock),
        ) as pool:
            for result in pool.imap_unordered(_worker, work):
                sid = result["subject_id"]
                state["subjects"][sid] = {
                    "status": result["status"],
                    "elapsed_sec": result["elapsed_sec"],
                    "error": result["error"],
                    "finished": result["finished"],
                }
                _save_state(state)
                counts[result["status"]] = counts.get(result["status"], 0) + 1
                mins = result["elapsed_sec"] / 60.0
                tail = f" — {result['error']}" if result["error"] else ""
                print(f"[{batch_id}] {sid}: {result['status']} ({mins:.1f} min){tail}")
    except KeyboardInterrupt:
        print(f"\n[batch] interrupted; checkpoint at {_state_path(batch_id)}")
        print(f"[batch] resume with: python3 -m regen_v3.batch_runner --resume {batch_id}")
        return 130

    elapsed = time.time() - t0
    live_calls = _read_max_extract_calls()
    print(
        f"\n=== batch {batch_id} done in {elapsed/60:.1f} min ===\n"
        f"  total:   {len(work)}\n"
        f"  merged:  {counts.get('merged', 0)}\n"
        f"  skipped: {counts.get('skipped', 0)}\n"
        f"  errors:  {counts.get('error', 0)}\n"
        f"  live LLM calls (parent proc only): {live_calls}\n"
        f"  state:   {_state_path(batch_id)}"
    )
    return 0 if counts.get("error", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
