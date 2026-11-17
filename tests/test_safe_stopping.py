"""Boundary tests for the study's conjunction and phase-local counters."""

import pandas as pd
import pytest

from asreview.models.stoppers import NConsecutiveIrrelevant
from asreview.webapp._safe_stopping import evaluate


def state(total=1000, phase="primary"):
    return {
        "phase": phase,
        "model": "elas_u4",
        "generation": "test",
        "ready": True,
        "total": total,
        "sample_target": 200,
        "sample_ids": list(range(200)),
        "phase_start_ids": list(range(200)),
        "key_record_ids": [0],
        "events": [],
    }


def labels(n=300, sample_relevant=10):
    return pd.DataFrame(
        {
            "record_id": range(n),
            "label": [1] * sample_relevant + [0] * (n - sample_relevant),
        }
    )


@pytest.mark.parametrize("n,stops", [(299, False), (300, True), (301, True)])
def test_exact_consecutive_boundary(n, stops):
    status = evaluate(state(), labels(n))
    assert status["stop"] is stops
    assert status["value"] == n - 200


@pytest.mark.parametrize("missing", ["keys", "estimate", "fraction", "streak"])
def test_every_condition_is_required(missing):
    config, data = state(), labels()
    if missing == "keys":
        config["key_record_ids"] = [999]
    elif missing == "estimate":
        data = labels(sample_relevant=100)
    elif missing == "fraction":
        config["total"] = 10000
        data = labels(sample_relevant=1)
    else:
        data.loc[250, "label"] = 1
    status = evaluate(config, data)
    assert not status["stop"]
    assert not next(check for check in status["checks"] if check["id"] == missing)[
        "met"
    ]


def test_inclusion_and_correction_recalculate_streak():
    data = labels(350)
    assert evaluate(state(), data)["stop"]
    data.loc[299, "label"] = 1
    status = evaluate(state(), data)
    assert status["value"] == 50
    assert not status["stop"]
    data.loc[299, "label"] = 0
    assert evaluate(state(), data)["stop"]


def test_secondary_has_fresh_counter_and_detects_primary_corrections():
    config = state(phase="secondary")
    config.update(
        primary_start_ids=list(range(200)),
        primary_stop_ids=list(range(300)),
        phase_start_ids=list(range(300)),
    )
    assert evaluate(config, labels(300))["value"] == 0
    assert not evaluate(config, labels(399))["stop"]
    assert evaluate(config, labels(400))["stop"]
    data = labels(400)
    data.loc[299, "label"] = 1
    status = evaluate(config, data)
    assert status["primary_invalidated"]
    assert status["blocked"]
    assert not status["stop"]


def test_rounding_and_sample_corrections():
    config = state(total=1001)
    data = labels(sample_relevant=1)
    status = evaluate(config, data)
    assert status["checks"][1]["target"] == 11
    assert status["checks"][2]["target"] == 101
    data.loc[0, "label"] = 0
    status = evaluate(config, data)
    assert status["blocked"]
    assert not status["stop"]


def test_exhaustion_is_not_a_successful_safe_stop():
    config = state(total=300)
    config["key_record_ids"] = [299]
    status = evaluate(config, labels())
    assert status["exhausted"]
    assert status["paused"]
    assert not status["stop"]


def test_legacy_stopper_also_stops_at_exactly_n():
    stopper = NConsecutiveIrrelevant(100)
    assert not stopper.stop(pd.DataFrame({"label": [0] * 99}), range(1000))
    assert stopper.stop(pd.DataFrame({"label": [0] * 100}), range(1000))
