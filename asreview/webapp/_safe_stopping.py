"""Persistent, server-enforced SAFE screening for this research fork.

The random sample, phase boundaries and audit events travel with .asreview
exports. Labels remain in ASReview's database, including its correction history.
All callers that mutate or serve screening state must hold ``project_lock``.
"""

import functools
import json
import math
import os
import secrets
import tempfile
import time
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

import numpy as np
from filelock import FileLock

from asreview.extensions import load_extension
from asreview.models import get_ai_config

STATE_FILE = "safe-stopping.json"
N_CONSECUTIVE = 100


@functools.lru_cache(maxsize=128)
def project_lock(path):
    # Reentrant within one request, shared between threads, and process-safe.
    return FileLock(Path(path) / "safe-stopping.lock", timeout=30)


def serialized(func):
    @functools.wraps(func)
    def wrapper(project, *args, **kwargs):
        with project_lock(str(project.project_path)):
            # A request may have waited while another request changed the model.
            project.__dict__.pop("_config", None)
            return func(project, *args, **kwargs)

    return wrapper


def load(project):
    path = project.project_path / STATE_FILE
    if not path.exists():
        return None
    try:
        state = json.loads(path.read_text())
        if state["version"] != 1 or state["phase"] not in (
            "random",
            "primary",
            "secondary",
        ):
            raise ValueError
        return state
    except (ValueError, KeyError, TypeError) as err:
        raise ValueError("Cannot read SAFE state; restore a project backup.") from err


def save(project, state):
    # A failed write must never leave a half-written state that disables the rule.
    with tempfile.NamedTemporaryFile(
        mode="w", dir=project.project_path, suffix=".tmp", delete=False
    ) as stream:
        json.dump(state, stream, indent=2, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
        name = stream.name
    os.replace(name, project.project_path / STATE_FILE)


def event(state, action, **details):
    state["events"].append({"action": action, "time": time.time(), **details})


def results(project):
    with project.db as db:
        return db.get_results_table().sort_values(["time", "record_id"], kind="stable")


def annotate_record(state, record):
    """Identify configured key studies, including other members of their group."""
    group_id = record.get("group_id", record["record_id"])
    record["is_key_study"] = bool(state and group_id in state["key_record_ids"])
    return record


def clear_pending(project):
    with project.db as db:
        for record_id in db.get_pending()["record_id"].tolist():
            db.delete_result(int(record_id))


def set_model(project, state, name):
    state["generation"] = uuid4().hex
    state["ready"] = False
    state["model"] = name
    project.update_review(model=asdict(get_ai_config(name)["value"]), model_name=name)
    project.remove_review_error()
    clear_pending(project)


def configure(project, payload):
    if load(project):
        raise ValueError("SAFE is already configured for this project.")
    if project.config["mode"] != "oracle":
        raise ValueError("SAFE is available for human screening projects only.")
    if not results(project).empty:
        raise ValueError(
            "Enable SAFE in a new, unlabeled project before adding prior knowledge "
            "or screening. Its initial sample must be random."
        )
    with project.db as db:
        groups = db.input[["record_id", "group_id"]]
    ids = sorted(int(x) for x in groups["group_id"].unique())
    if not ids:
        raise ValueError("Upload a dataset before enabling SAFE.")
    keys = payload.get("key_record_ids")
    if not isinstance(keys, list) or any(type(x) is not int for x in keys):
        raise ValueError("Key studies must be a list of record identifiers.")
    group_map = dict(zip(groups["record_id"], groups["group_id"], strict=True))
    if any(x not in group_map for x in keys):
        raise ValueError("A key study does not belong to this dataset.")
    keys = sorted({int(group_map[x]) for x in keys})
    if not keys and payload.get("no_key_studies") is not True:
        raise ValueError("Select key studies, or confirm none are present.")
    seed = secrets.randbits(32)
    order = np.random.default_rng(seed).permutation(ids).tolist()
    state = {
        "version": 1,
        "phase": "random",
        "generation": uuid4().hex,
        "ready": True,
        "model": "random",
        "total": len(ids),
        "key_record_ids": keys,
        "random_seed": seed,
        "random_order": order,
        "sample_target": min(len(ids), max(200, math.ceil(len(ids) / 100))),
        "sample_ids": [],
        "phase_start_ids": [],
        "primary_stop_ids": [],
        "events": [],
    }
    event(state, "enabled", key_record_ids=keys, random_seed=seed)
    # Save the guard before changing the queue. Recovery reconstructs this exact
    # seeded order if configuration is interrupted.
    save(project, state)
    clear_pending(project)
    with project.db as db:
        db.add_last_ranking(order, None, "random", None, None)
    project.update_review(status="review")
    return state


def streak(labels):
    count = 0
    for label in reversed(list(labels)):
        if label != 0:
            break
        count += 1
    return count


def evaluate(state, labeled):
    """Calculate status from current labels, never from a cached counter."""
    labels = dict(
        zip(labeled["record_id"].astype(int), labeled["label"].astype(int), strict=True)
    )
    sample_ids = state["sample_ids"] or (
        list(labels) if state["phase"] == "random" else []
    )
    sample = [labels[x] for x in sample_ids if x in labels]
    n_sample = len(sample)
    n_relevant = sum(sample)
    sample_valid = (
        n_sample >= state["sample_target"]
        and 0 < n_relevant < n_sample
        and n_sample == len(sample_ids)
    )
    total = state["total"]
    estimate = total * n_relevant / n_sample if n_sample else None
    twice_estimate = (
        (2 * total * n_relevant + n_sample - 1) // n_sample if n_sample else None
    )
    key_found = sum(labels.get(x) == 1 for x in state["key_record_ids"])
    phase_labels = labeled[~labeled["record_id"].isin(state["phase_start_ids"])]
    consecutive = streak(phase_labels["label"])
    checks = [
        {
            "id": "keys",
            "label": "Key studies marked relevant",
            "value": key_found,
            "target": len(state["key_record_ids"]),
            "met": key_found == len(state["key_record_ids"]),
        },
        {
            "id": "estimate",
            "label": "Screened: twice the estimated relevant total",
            "value": len(labels),
            "target": twice_estimate,
            "met": sample_valid and len(labels) >= twice_estimate,
        },
        {
            "id": "fraction",
            "label": "Screened: at least 10% of the dataset",
            "value": len(labels),
            "target": math.ceil(total / 10),
            "met": len(labels) >= math.ceil(total / 10),
        },
        {
            "id": "streak",
            "label": "Consecutive exclusions in this phase",
            "value": consecutive,
            "target": N_CONSECUTIVE,
            "met": consecutive >= N_CONSECUTIVE,
        },
    ]
    invalidated = False
    if state["phase"] == "secondary":
        # Corrections must not silently invalidate the primary stopping decision.
        primary = labeled[labeled["record_id"].isin(state["primary_stop_ids"])]
        primary_streak = streak(
            primary[~primary["record_id"].isin(state["primary_start_ids"])]["label"]
        )
        invalidated = not (
            sample_valid
            and checks[0]["met"]
            and len(primary) >= twice_estimate
            and len(primary) >= math.ceil(total / 10)
            and primary_streak >= N_CONSECUTIVE
        )
    exhausted = len(labels) >= total
    stop = (
        state["phase"] != "random"
        and sample_valid
        and not invalidated
        and all(check["met"] for check in checks)
    )
    blocked = invalidated or (state["phase"] != "random" and not sample_valid)
    return {
        "id": "safe",
        "phase": state["phase"],
        "model": state["model"],
        "params": {"n": N_CONSECUTIVE},
        "value": consecutive,
        "stop": bool(stop),
        "exhausted": exhausted,
        "blocked": bool(blocked),
        "paused": bool(stop or exhausted or blocked),
        "ready": state["ready"],
        "generation": state["generation"],
        "checks": checks,
        "total": total,
        "screened": len(labels),
        "sample_count": n_sample,
        "sample_target": state["sample_target"],
        "sample_relevant": n_relevant,
        "estimated_relevant": estimate,
        "key_record_ids": state["key_record_ids"],
        "primary_invalidated": bool(invalidated),
        "events": state["events"],
    }


def refresh(project, state):
    """Recover transitions after a restart and record newly reached boundaries."""
    labeled = results(project)
    status = evaluate(state, labeled)
    if state["phase"] == "random":
        if (
            len(labeled) >= state["sample_target"]
            and labeled["label"].nunique() == 2
            and not status["exhausted"]
        ):
            state["sample_ids"] = labeled["record_id"].astype(int).tolist()
            state["phase_start_ids"] = state["sample_ids"].copy()
            state["phase"] = "primary"
            event(
                state,
                "random_sample_complete",
                sample_ids=state["sample_ids"],
                relevant=status["sample_relevant"],
                estimated_relevant=status["estimated_relevant"],
            )
            set_model(project, state, "elas_u4")
            save(project, state)
            status = evaluate(state, labeled)
    reached = bool(status["paused"])
    if reached != state.get("was_paused", False):
        state["was_paused"] = reached
        event(
            state,
            "paused" if reached else "pause_cleared",
            phase=state["phase"],
            screened=status["screened"],
            checks=status["checks"],
            exhausted=status["exhausted"],
            blocked=status["blocked"],
        )
        save(project, state)
    return status


def transition(project, state, action):
    status = refresh(project, state)
    labeled = results(project)
    if action == "secondary":
        if state["phase"] != "primary" or not status["stop"] or status["exhausted"]:
            raise ValueError("Complete all primary SAFE conditions first.")
        # Check availability before changing any phase or queue state.
        try:
            load_extension("models.feature_extractors", "multilingual-e5-large")
        except (ImportError, ValueError) as err:
            raise ValueError(
                "ELAS l2 needs asreview-dory. Install it in this ASReview "
                "environment, restart LAB, and try again."
            ) from err
        state["primary_start_ids"] = state["phase_start_ids"].copy()
        state["primary_stop_ids"] = labeled["record_id"].astype(int).tolist()
        state["phase_start_ids"] = state["primary_stop_ids"].copy()
        state["phase"] = "secondary"
        set_model(project, state, "elas_l2")
    elif action == "reopen_primary":
        if not status["primary_invalidated"]:
            raise ValueError("The primary stopping decision has not been invalidated.")
        state["phase_start_ids"] = labeled["record_id"].astype(int).tolist()
        state["phase"] = "primary"
        set_model(project, state, "elas_u4")
    elif action == "retry":
        if state["phase"] == "random" or status["paused"]:
            raise ValueError("There is no model training to retry.")
        set_model(project, state, state["model"])
    else:
        raise ValueError("Unknown SAFE action.")
    state["was_paused"] = False
    event(state, action, phase=state["phase"], screened=len(labeled))
    save(project, state)
    return evaluate(state, labeled)


def invalidate_ranking(project, state, record_id, old_label, new_label):
    event(
        state,
        "label_corrected",
        record_id=record_id,
        old_label=old_label,
        new_label=new_label,
    )
    if state["phase"] != "random":
        set_model(project, state, state["model"])
    save(project, state)
