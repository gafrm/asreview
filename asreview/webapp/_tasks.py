# Copyright 2019-2025 The ASReview Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import sqlite3

import asreview as asr
from asreview.models import get_ai_config
from asreview.models.queriers import TopDown
from asreview.models.stoppers import IsFittable
from asreview.simulation.simulate import Simulate
from asreview.webapp import _safe_stopping as safe
from asreview.webapp.utils import get_project_path


def _read_cycle_data(project):
    return asr.ActiveLearningCycleData(**project.get_model_config())


def run_task(project_id, simulation=False):
    project_path = get_project_path(project_id)

    with asr.Project(project_path, project_id=project_id) as project:
        if simulation:
            run_simulation(project)
        else:
            run_model(project)

    return True


def run_model(project):
    with safe.project_lock(str(project.project_path)):
        project.__dict__.pop("_config", None)
        state = safe.load(project)
        if state and state["phase"] == "random":
            return
        generation = state["generation"] if state else None
        cycle_data = (
            get_ai_config(state["model"])["value"]
            if state
            else _read_cycle_data(project)
        )
        with project.db as db:
            if not db.exist_new_labeled_records and not (state and not state["ready"]):
                return

            labeled = db.get_results_table(columns=["record_id", "label"])
            if labeled["label"].nunique() < 2:
                if state:
                    project.set_review_error(
                        ValueError("Training needs both label classes.")
                    )
                return

    try:
        if cycle_data.feature_extractor:
            try:
                fm = project.get_feature_matrix(cycle_data.feature_extractor)
                cycle = asr.ActiveLearningCycle.from_meta(
                    cycle_data, skip_feature_extraction=True
                )
            except ValueError:
                cycle = asr.ActiveLearningCycle.from_meta(cycle_data)
                fm = cycle.transform(project.db.input.get_df())
                with safe.project_lock(str(project.project_path)):
                    current = safe.load(project)
                    if (current["generation"] if current else None) != generation:
                        return
                    project.__dict__.pop("_config", None)
                    project.add_feature_matrix(fm, cycle.feature_extractor.name)
        else:
            cycle = asr.ActiveLearningCycle.from_meta(cycle_data)
            fm = project.db.input.get_df().values

        if cycle.classifier is not None:
            cycle.fit(
                fm[labeled["record_id"].values],
                labeled["label"].values,
            )

        ranked_record_ids = cycle.rank(fm)

        with safe.project_lock(str(project.project_path)):
            current = safe.load(project)
            if (current["generation"] if current else None) != generation:
                return  # An old model must not overwrite the next phase's ranking.
            with project.db as db:
                previous = db.get_last_ranking_table()["training_set"].dropna()
                if (
                    current
                    and current["ready"]
                    and not previous.empty
                    and previous.max() > len(labeled)
                ):
                    return  # Another job already trained on more decisions.
                db.add_last_ranking(
                    ranked_record_ids,
                    cycle_data.classifier
                    if cycle_data.classifier is not None
                    else None,
                    cycle_data.querier,
                    cycle_data.balancer if cycle_data.balancer is not None else None,
                    cycle_data.feature_extractor
                    if cycle_data.feature_extractor is not None
                    else None,
                    len(labeled),
                )
            if current and not current["ready"]:
                current["ready"] = True
                safe.event(
                    current,
                    "ranking_ready",
                    phase=current["phase"],
                    model=current["model"],
                    training_set=len(labeled),
                )
                safe.save(project, current)
            project.remove_review_error()

    except Exception as err:
        # Transient SQLite lock contention is self-healing: the next label event
        # re-triggers training, so don't surface it as an error to the user.
        if isinstance(err, sqlite3.OperationalError) and "locked" in str(err).lower():
            return
        with safe.project_lock(str(project.project_path)):
            current = safe.load(project)
            if (current["generation"] if current else None) != generation:
                return
            project.set_review_error(err)
        raise


def run_simulation(project):
    with project.db as db:
        priors = db.get_priors()["record_id"].tolist()

    cycles = [
        asr.ActiveLearningCycle(
            querier=TopDown(),
            stopper=IsFittable(),
        ),
        asr.ActiveLearningCycle.from_meta(_read_cycle_data(project)),
    ]

    sim = Simulate(
        project.db.input.get_df(),
        project.db.input["included"],
        cycles,
        print_progress=False,
        groups=project.db.input.get_groups(),
    )
    try:
        sim.label(priors)
        sim.review()
    except Exception as err:
        project.set_review_error(err)
        raise

    project.update_review(status="finished")
    sim.to_sql(project.db_path)
