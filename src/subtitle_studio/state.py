"""Stage completion tracking for resumable runs.

`state.json` records, per stage, when it completed and the SHA-256 of every input
it consumed (artifact files + the config sections it depends on). `run` recomputes
those hashes and skips stages whose inputs are unchanged; editing styles.toml or
renaming a speaker therefore invalidates exactly the stages that consumed them.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from subtitle_studio.paths import state_path


def hash_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def hash_obj(obj: Any) -> str:
    canonical = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def load_state(workdir: Path) -> dict:
    p = state_path(workdir)
    if not p.exists():
        return {"stages": {}}
    return json.loads(p.read_text(encoding="utf-8"))


def save_state(workdir: Path, state: dict) -> None:
    p = state_path(workdir)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def stage_fresh(state: dict, stage: str, current_inputs: dict[str, str]) -> bool:
    """True if `stage` completed with exactly these input hashes."""
    entry = state.get("stages", {}).get(stage)
    return entry is not None and entry.get("inputs") == current_inputs


def record_stage(workdir: Path, stage: str, inputs: dict[str, str]) -> None:
    state = load_state(workdir)
    state.setdefault("stages", {})[stage] = {
        "completed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "inputs": inputs,
    }
    save_state(workdir, state)


def invalidate_from(workdir: Path, stage: str, order: list[str]) -> None:
    """Drop `stage` and everything after it in the pipeline `order`."""
    state = load_state(workdir)
    stages = state.get("stages", {})
    if stage in order:
        for name in order[order.index(stage):]:
            stages.pop(name, None)
    save_state(workdir, state)
