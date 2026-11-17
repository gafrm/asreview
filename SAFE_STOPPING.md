# SAFE screening in this fork

This branch extends ASReview LAB 3.0.8 with automatic, server-enforced stopping
for human screening. Choose **Start SAFE screening** during project setup.
Ordinary projects keep their existing workflow. SAFE is opt-in and must be
enabled on a new, unlabeled project, before adding prior knowledge.

## Screening procedure

1. Upload the dataset. Use separate projects for the English and French datasets.
2. Search for and select the predefined key studies present in that dataset.
   Selecting a study does not label it or change its position in the queue. If
   none are present, explicitly check the corresponding box.
   Selected seed/key articles have an amber-tinted card, amber border and a
   **Predefined key study (seed article)** banner when they appear during
   screening or in the history. Excluding one requires an explicit confirmation,
   including with the keyboard shortcut or when correcting a history decision.
   Confirmed exclusions are logged; the article remains a key study and its
   stopping condition remains unmet while it is excluded. Relevant decisions
   remain manual and need only one click.
3. Start SAFE screening. A seeded random order is saved in the project. Screen
   at least `max(200, ceil(N / 100))` units (capped at N), extending the random
   phase until at least one relevant and one irrelevant unit have been labeled.
4. The application stores the sample membership and computes the preliminary
   relevant total as `N * sample_relevant / sample_screened`. It trains ELAS u4
   and waits for its ranking before serving the next record.
5. Primary screening pauses automatically only when **all four** conditions hold:

   | Condition | Calculation |
   | --- | --- |
   | All predefined key studies found | Every selected study is marked relevant |
   | Twice the estimated relevant total screened | Screened >= ceil(2 * N * sample_relevant / sample_screened) |
   | At least 10% screened | Screened >= ceil(N / 10) |
   | 100 consecutive exclusions | At least 100 new consecutive exclusions in the current primary phase |

   The screened total includes the random sample; the consecutive-exclusion
   counter starts after it. An inclusion resets the counter. A threshold above
   the dataset size is not silently capped: dataset exhaustion is reported as
   such, separately from meeting SAFE's conditions.
   A compact tracker for all four conditions stays visible above the article:
   green **Met** indicators and outlined **Pending** indicators show each
   current count and target. **Show criteria** expands the calculation details.
6. Click **Start ELAS l2 check**. Existing labels are preserved, pending unlabeled
   records are released, and screening waits for the new model's ranking. The
   exclusion counter starts from zero. An inclusion resets it. This phase also
   pauses automatically at 100 consecutive new exclusions.
7. Export the `.asreview` project and the screening decisions. **The independent
   TF-IDF/Naive Bayes quality-control review of exclusions and citation chaining
   are separate protocol steps; they are not automated by this change.** A
   second-model pause does not mean that those steps have been completed.

ASReview groups duplicate records. All SAFE denominators, samples, counters,
and key-study checks use one representative per duplicate group. This avoids
counting an inherited duplicate label as another independent screening decision.
The interface reports this number as *screening units*; retain it with the
original import count when reporting the review.

## Corrections, restarts and concurrent tabs

- Current labels, not a cached counter, determine every stopping decision.
  Correcting a sample label updates the preliminary estimate. The original
  sample estimate and correction events remain in the project audit trail.
- Correcting a label forces a fresh ranking. If a primary label is corrected
  during the second-model phase and invalidates the original stop, screening
  pauses. **Return to ELAS u4 with a fresh counter** preserves all labels and
  requires 100 new exclusions. Review the original decision before using it.
- If corrections remove one of the random sample's two classes, screening
  remains blocked. Resolve incorrect labels or start a new project with the
  amended sampling procedure; the program does not invent an estimate.
- SAFE serializes screening requests and shares one pending record across tabs.
  It supports one sequential screening stream per project, not independent
  simultaneous reviewers. A stale tab cannot relabel a completed record or
  submit a new decision past the stopping boundary. History corrections remain
  available through the normal history interface.
- `safe-stopping.json` in the project stores the seed, sample membership, phase
  boundaries, key studies, and timestamped events. ASReview's existing database
  stores decisions and correction history. Export/reimport preserves both.
  Keep using this fork when reopening a SAFE project; upstream ASReview does
  not enforce this fork's additional state file.
- Direct model changes and ordinary threshold changes are disabled for SAFE
  projects so the protocol cannot be accidentally replaced during screening.

## Install on Windows

Install Git, Python 3.12 (or 3.13), and Node.js 24.
Run these commands in PowerShell from the parent folder where you want the code:

```powershell
git clone --branch safe-stopping https://github.com/gafrm/asreview.git asreview-safe
Set-Location asreview-safe
powershell -ExecutionPolicy Bypass -File .\scripts\install-safe.ps1
.\.venv\Scripts\asreview.exe lab
```

The execution-policy option applies only to this installer process. The script
creates an isolated Python environment and builds the modified browser
interface; `pip install` alone does not build the frontend. For Python 3.13,
append `-PythonVersion 3.13` to the installer command.

ELAS l2 requires `asreview-dory` (installed by default) and a substantial model
download on first use. Keep the computer online for that first download. If
training fails, the review remains paused and exposes a retry button. The
optional `-SkipDory` installer flag is for development of the primary phase only;
it does not provide a functioning second-model check.

For a disposable trial, import a small dummy dataset into a separate project.
Do not practice by labeling records in the real review project. Before upgrading
any existing ASReview installation, export its projects as backups.

## Development and verification

```sh
python -m venv .venv
.venv/bin/python -m pip install -e '.[test,lint]'
cd asreview/webapp
CYPRESS_INSTALL_BINARY=0 HUSKY=0 npm ci
npm run build
CI=true npm test -- --watchAll=false --runInBand SafeStopping.test.js
cd ../..
.venv/bin/python -m pytest tests/test_safe_stopping.py asreview/webapp/tests/test_api/test_safe_stopping.py
```

The API tests exercise real primary TF-IDF/SVM training, the four-condition
conjunction, exact thresholds, sample extension, corrections, queue enforcement,
export/reimport, and phase changes. The second-model integration test substitutes
a small feature extractor for the large downloaded embedding model; it tests
the phase/ranking machinery without downloading the pretrained weights. The
full ELAS l2 model and the Windows installation require a smoke test on the
screening computer before production use.

Development validation used Linux, Python 3.12 and Node.js 24: 21 SAFE unit/API
tests, 12 React component tests and 68 core regression tests passed. The production
frontend compiled, and an independently installed wheel successfully imported
the SAFE backend and served the compiled interface. The cloud browser could not
reach the local development server, so a visual browser check remains part of
the installation smoke test.
