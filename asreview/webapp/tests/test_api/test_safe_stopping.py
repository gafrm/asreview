"""Exercise SAFE via the same endpoints used by the screening UI."""

from io import BytesIO
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest

import asreview as asr
from asreview.webapp import _safe_stopping as safe
from asreview.webapp._tasks import run_model
from asreview.webapp.utils import get_project_path


@pytest.fixture
def review(client_no_auth, monkeypatch):
    data = pd.DataFrame(
        {
            "title": [f"Publication number {i} topic {i % 19}" for i in range(1000)],
            "abstract": [
                f"Word variation and diffusion in corpus {i}" for i in range(1000)
            ],
        }
    )
    response = client_no_auth.post(
        "/api/projects/create",
        data={
            "mode": "oracle",
            "file": (BytesIO(data.to_csv(index=False).encode()), "safe.csv"),
        },
    )
    assert response.status_code == 201, response.json
    project_id = response.json["id"]
    project = asr.Project(get_project_path(project_id), project_id=project_id)
    # Queue models explicitly in these tests. The actual primary model is trained
    # at the phase boundary, not redundantly after each synthetic label.
    monkeypatch.setattr("asreview.webapp._api.projects._run_model", Mock())
    yield client_no_auth, project, f"/api/projects/{project_id}"
    project.close()


def enable(review):
    client, project, url = review
    response = client.post(
        url + "/safe", json={"key_record_ids": [], "no_key_studies": True}
    )
    assert response.status_code == 201, response.json
    return response.json


def screen(review, label):
    client, project, url = review
    response = client.get(url + "/get_record")
    assert response.status_code == 200, response.json
    assert response.json["status"] == "review", response.json
    record_id = response.json["result"]["record_id"]
    response = client.post(
        url + f"/record/{record_id}",
        data={
            "record_id": record_id,
            "label": label,
            "retrain_model": "true",
        },
    )
    assert response.status_code == 200, response.json
    return record_id


def complete_sample(review):
    for i in range(200):
        screen(review, int(i < 10))


def test_full_primary_pause_restart_and_export(review, tmp_path):
    client, project, url = review
    enable(review)
    complete_sample(review)
    status = client.get(url + "/stopping").json
    assert status["phase"] == "primary"
    assert status["estimated_relevant"] == 50
    assert status["value"] == 0
    assert not status["ready"]
    assert client.get(url + "/get_record").json["status"] == "safe_training"
    run_model(project)  # Real TF-IDF/SVM training with the same label count.
    assert safe.load(project)["ready"]
    for _ in range(99):
        screen(review, 0)
    assert not client.get(url + "/stopping").json["stop"]
    last_id = screen(review, 0)
    response = client.get(url + "/get_record")
    assert response.json["status"] == "safe_paused"
    assert response.json["result"] is None
    assert response.json["stopping"]["value"] == 100
    # A stale tab cannot submit another label after the threshold.
    response = client.post(
        url + f"/record/{last_id}", data={"record_id": last_id, "label": 0}
    )
    assert response.status_code == 409
    assert len(safe.results(project)) == 300
    with project.db as db:
        assert db.get_pending().empty

    export = tmp_path / "screening.asreview"
    project.export(export)
    restored = asr.Project.load(export, tmp_path / "restored")
    status = safe.refresh(restored, safe.load(restored))
    assert status["stop"]
    assert status["screened"] == 300
    assert status["value"] == 100
    assert any(event["action"] == "paused" for event in status["events"])
    restored.close()
    # Correcting a recent exclusion reopens the primary phase and forces a
    # ranking based on the changed labels, even though label count is unchanged.
    response = client.put(
        url + f"/record/{last_id}", data={"record_id": last_id, "label": 1}
    )
    assert response.status_code == 200
    status = client.get(url + "/stopping").json
    assert not status["stop"]
    assert status["value"] == 0
    assert not status["ready"]
    run_model(project)
    assert client.get(url + "/get_record").json["status"] == "review"


def test_random_sample_extends_until_both_classes_and_blocks_overrides(review):
    client, project, url = review
    enable(review)
    for _ in range(200):
        screen(review, 0)
    assert client.get(url + "/stopping").json["phase"] == "random"
    run_model(project)
    with project.db as db:
        assert set(db.get_last_ranking_table()["querier"]) == {"random"}
    for endpoint, payload in [
        ("/learner", {"name": "elas_u3"}),
        ("/train", {"ranking": "top_down"}),
        ("/stopping", {"n": 1}),
    ]:
        assert client.post(url + endpoint, data=payload).status_code == 400
    assert client.put(url + "/review", data={"status": "finished"}).status_code == 400
    screen(review, 1)
    status = client.get(url + "/stopping").json
    assert status["phase"] == "primary"
    assert status["sample_count"] == 201
    assert status["sample_relevant"] == 1


def test_shared_pending_and_stale_tab_cannot_relabel(review):
    client, project, url = review
    enable(review)
    first = client.get(url + "/get_record").json["result"]["record_id"]
    second = client.get(url + "/get_record").json["result"]["record_id"]
    assert first == second
    screen(review, 0)
    response = client.post(
        url + f"/record/{first}", data={"record_id": first, "label": 1}
    )
    assert response.status_code == 400
    assert safe.results(project).iloc[0]["label"] == 0


def test_configuration_validation(review):
    client, project, url = review
    for payload in (
        {},
        {"key_record_ids": []},
        {"key_record_ids": [99999]},
        {"key_record_ids": [True]},
    ):
        assert client.post(url + "/safe", json=payload).status_code == 400
    assert safe.load(project) is None
    enable(review)
    assert client.post(url + "/safe", json={"key_record_ids": [0]}).status_code == 400


def test_unavailable_secondary_model_does_not_change_phase(review, monkeypatch):
    client, project, url = review
    enable(review)
    # The complete HTTP screening path is covered by the end-to-end tests.
    with project.db as db:
        for i, record_id in enumerate(safe.load(project)["random_order"][:200]):
            db.label_record(record_id, int(i < 10))
    config = safe.load(project)
    safe.refresh(project, config)
    with project.db as db:
        for record_id in config["random_order"][200:300]:
            db.label_record(record_id, 0)
    before = safe.load(project)
    monkeypatch.setattr(
        safe, "load_extension", Mock(side_effect=ValueError("Install asreview-dory"))
    )
    response = client.post(url + "/safe/transition", json={"action": "secondary"})
    assert response.status_code == 400
    after = safe.load(project)
    assert after["phase"] == "primary"
    assert after["generation"] == before["generation"]


def test_old_training_job_cannot_replace_new_phase_ranking(review, monkeypatch):
    client, project, url = review
    enable(review)
    with project.db as db:
        for i, record_id in enumerate(safe.load(project)["random_order"][:200]):
            db.label_record(record_id, int(i < 10))
    safe.refresh(project, safe.load(project))
    original_rank = asr.ActiveLearningCycle.rank

    def rank_after_new_generation(cycle, matrix):
        config = safe.load(project)
        safe.set_model(project, config, "elas_u4")
        safe.save(project, config)
        return original_rank(cycle, matrix)

    monkeypatch.setattr(asr.ActiveLearningCycle, "rank", rank_after_new_generation)
    run_model(project)
    assert not safe.load(project)["ready"]
    with project.db as db:
        assert set(db.get_last_ranking_table()["querier"]) == {"random"}


def test_small_dataset_exhaustion_and_duplicate_units(client_no_auth):
    data = pd.DataFrame(
        {
            "title": [
                "First unique paper",
                "Second unique paper",
                "First unique paper",
            ],
            "abstract": [
                "Lexical innovation in France",
                "Historical syntax in Canada",
                "Lexical innovation in France",
            ],
        }
    )
    response = client_no_auth.post(
        "/api/projects/create",
        data={
            "mode": "oracle",
            "file": (BytesIO(data.to_csv(index=False).encode()), "small.csv"),
        },
    )
    project_id = response.json["id"]
    project = asr.Project(get_project_path(project_id), project_id=project_id)
    url = f"/api/projects/{project_id}"
    review = client_no_auth, project, url
    response = client_no_auth.post(url + "/safe", json={"key_record_ids": [2]})
    assert response.status_code == 201
    status = response.json
    assert status["key_record_ids"] == [0]
    assert status["total"] == 2
    assert status["sample_target"] == 2
    for _ in range(2):
        record = client_no_auth.get(url + "/get_record").json["result"]
        screen(review, int(record["is_key_study"]))
    status = client_no_auth.get(url + "/get_record").json
    assert status["status"] == "safe_paused"
    assert status["stopping"]["exhausted"]
    assert not status["stopping"]["stop"]
    with project.db as db:
        assert len(db.get_results_table()) == 2
        assert len(db.get_results_table(groups=True)) == 3
    project.close()


def test_key_article_marking_confirmation_and_history(review, monkeypatch):
    client, project, url = review
    monkeypatch.setattr(safe.secrets, "randbits", lambda _: 42)
    key_id = int(np.random.default_rng(42).permutation(range(1000))[0])
    response = client.post(url + "/safe", json={"key_record_ids": [key_id]})
    assert response.status_code == 201
    record = client.get(url + "/get_record").json["result"]
    assert record["record_id"] == key_id and record["is_key_study"]
    endpoint = url + f"/record/{key_id}"
    decision = {"record_id": key_id, "label": 0}
    # Clicking or a stale client cannot silently exclude a key article.
    response = client.post(endpoint, data=decision)
    assert response.status_code == 409
    assert response.json["requires_key_exclusion_confirmation"]
    assert safe.results(project).empty
    assert client.get(url + "/get_record").json["result"]["record_id"] == key_id
    decision["confirm_key_exclusion"] = "true"
    assert client.post(endpoint, data=decision).status_code == 200
    assert safe.results(project).iloc[0]["label"] == 0
    events = safe.load(project)["events"]
    assert sum(event["action"] == "key_study_excluded" for event in events) == 1
    history = client.get(url + "/labeled").json["result"]
    assert history[0]["is_key_study"]
    # Editing tags on an already excluded key does not request another confirmation.
    assert (
        client.put(
            endpoint, data={"record_id": key_id, "label": 0, "tags": "[]"}
        ).status_code
        == 200
    )
    # Including it needs no confirmation. Reversing that decision does.
    included = client.put(endpoint, data={"record_id": key_id, "label": 1})
    assert included.status_code == 200 and included.json["result"]["is_key_study"]
    assert (
        client.put(endpoint, data={"record_id": key_id, "label": 0}).status_code == 409
    )
    assert safe.results(project).iloc[0]["label"] == 1
    assert client.put(endpoint, data=decision).status_code == 200
    events = safe.load(project)["events"]
    assert sum(event["action"] == "key_study_excluded" for event in events) == 2
    other = client.get(url + "/get_record").json["result"]
    assert not other["is_key_study"]
    screen(review, 0)  # Ordinary records keep one-click exclusion.


def test_secondary_clears_counter_forces_new_ranking_and_pauses(review, monkeypatch):
    client, project, url = review
    enable(review)
    complete_sample(review)
    run_model(project)
    primary_ids = [screen(review, 0) for _ in range(100)]
    # The extension is optional. Stub only its expensive embedding transform;
    # the actual task, classifier, ranking write and phase guards still run.
    from asreview.extensions import load_extension as original_load
    from asreview.models.feature_extractors import Tfidf

    def extension(kind, name):
        if kind == "models.feature_extractors" and name == "multilingual-e5-large":

            class SmallEmbedding(Tfidf):
                name = "multilingual-e5-large"

                def __init__(self, normalize=True):
                    self.normalize = normalize
                    super().__init__()

            return SmallEmbedding
        return original_load(kind, name)

    monkeypatch.setattr(safe, "load_extension", extension)
    monkeypatch.setattr("asreview.learner.load_extension", extension)
    response = client.post(url + "/safe/transition", json={"action": "secondary"})
    assert response.status_code == 200, response.json
    assert response.json["value"] == 0
    assert not response.json["ready"]
    assert client.get(url + "/get_record").json["status"] == "safe_training"
    run_model(project)
    with project.db as db:
        assert set(db.get_last_ranking_table()["feature_extractor"]) == {
            "multilingual-e5-large"
        }
    secondary_id = screen(review, 1)
    for _ in range(100):
        screen(review, 0)
    status = client.get(url + "/stopping").json
    assert status["phase"] == "secondary"
    assert status["stop"] and status["value"] == 100
    assert client.get(url + "/get_record").json["result"] is None
    # Corrected primary labels invalidate the earlier transition, not just the
    # secondary counter, and a restart must preserve this protection.
    last_primary = primary_ids[-1]
    client.put(
        url + f"/record/{last_primary}", data={"record_id": last_primary, "label": 1}
    )
    status = client.get(url + "/stopping").json
    assert status["primary_invalidated"] and status["blocked"]
    assert not status["stop"]
    response = client.post(url + "/safe/transition", json={"action": "reopen_primary"})
    assert response.status_code == 200
    assert response.json["phase"] == "primary"
    assert response.json["value"] == 0
    with project.db as db:
        assert db.get_results_record(secondary_id).iloc[0]["label"] == 1
