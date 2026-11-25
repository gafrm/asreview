# SAFE screening in this fork

This branch extends ASReview LAB 3.0.8 with automatic, server-enforced stopping
for human screening. Choose **Start SAFE screening** during project setup.
Ordinary projects keep their existing workflow. SAFE is opt-in and must be
enabled on a new, unlabeled project, before adding prior knowledge.

## Configurable thresholds

Before starting SAFE screening, set the six numerical parameters in the setup
screen. The defaults below reproduce the submitted scoping-review protocol V2.

| Parameter | Default |
| --- | ---: |
| Minimum random sample count | 200 |
| Minimum random sample percentage | 1% |
| Estimated relevant total multiplier | 2 |
| Minimum percentage screened | 10% |
| Primary consecutive exclusions (ELAS u4) | 100 |
| Secondary consecutive exclusions (ELAS l2) | 100 |

All six accept positive integers; percentages cannot exceed 100. The random
sample target is the larger of the minimum count and the rounded-up percentage,
capped at the number of screening units. Both relevance classes must still be
represented before active learning starts. All four primary stopping conditions
remain mandatory. The primary and secondary models remain ELAS u4 and ELAS l2.
The setup screen can restore the defaults before screening starts.

The server validates and locks the parameters when SAFE is enabled. The selected
values are saved in `safe-stopping.json` and its configuration audit event,
and survive project export and reimport. Existing projects without stored
parameters retain the original defaults. Use a new project for a different
configuration; do not edit the state file to change an ongoing review.

## Screening procedure

1. Upload the dataset. Use separate projects for the English and French datasets.
2. Click **Import seed list (CSV/RIS)** to upload your predefined key studies,
   or search for and select individual studies present in that dataset.
   Selecting a study does not label it or change its position in the queue. If
   none are present, explicitly check the corresponding box.
   Selected seed/key articles have an amber-tinted card, amber border and a
   **Predefined key study (seed article)** banner when they appear during
   screening or in the history. Excluding one requires an explicit confirmation,
   including with the keyboard shortcut or when correcting a history decision.
   Confirmed exclusions are logged; the article remains a key study and its
   stopping condition remains unmet while it is excluded. Relevant decisions
   remain manual and need only one click.
3. Configure thresholds and start SAFE screening. A seeded random order is saved
   in the project. With the defaults, screen at least
   `max(200, ceil(N / 100))` units (capped at N), extending the random
   phase until at least one relevant and one irrelevant unit have been labeled.
4. The application stores the sample membership and computes the preliminary
   relevant total as `N * sample_relevant / sample_screened`. It trains ELAS u4
   and waits for its ranking before serving the next record.
5. Primary screening pauses automatically only when **all four** conditions hold.
   The following table shows the default thresholds; the evaluator and tracker
   use the actual configured values:

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
   pauses automatically at the configured secondary threshold (default: 100)
   consecutive new exclusions.
7. Export the `.asreview` project and the screening decisions. **The independent
   TF-IDF/Naive Bayes quality-control review of exclusions and citation chaining
   are separate protocol steps; they are not automated by this change.** A
   second-model pause does not mean that those steps have been completed.

## Optional duplicate grouping

Before uploading a local dataset, uncheck **Automatically group duplicate
records** if the bibliography has already been deduplicated externally. The
default remains enabled for compatibility with ordinary ASReview projects.
The choice is stored as `automatic_deduplication` in project.json and is
locked at import. Existing projects retain their stored duplicate assignments;
create a fresh project to change the policy. The creation API accepts the form
field `automatic_deduplication` with the literal value `true` or `false`.
Other import routes retain automatic grouping by default.

When grouping is enabled, SAFE denominators, samples, counters and key-study
checks use one representative per group. When disabled, each imported record
is an independent screening unit and receives its own decision. The dataset
statistics report persisted group assignments rather than recalculating them.
Unicode letters and digits are retained in duplicate-text normalization, but
automatic grouping remains a heuristic, not a substitute for adjudication.

For the English scoping-review corpus, disable grouping after the reviewed
BibDedupe procedure. The 12,340-record export originally received 12 additional
automatic assignments, including five clearly distinct publications in
non-Latin scripts. After Unicode normalization the count was seven; with
grouping disabled the user confirmed no hidden duplicates in a fresh import.
Retain the import count, policy and screening-unit count for reporting.

## Importing a seed list

Upload a CSV or RIS bibliography before starting SAFE. For CSV, use a `doi`
column, a `title` column, or both; `authors` and `year` are optional. Column
names are case-insensitive. Comma, semicolon and tab separators are supported.
Each entry needs at least a DOI or title. A CSV exported from Excel should use
UTF-8; UTF-16 with a byte-order mark and Windows-1252 are also accepted.
RIS uses the normal title, DOI, author and year fields. Labels embedded in a
RIS bibliography are ignored: seed selection never labels an article.
The limit is 1,000 seed entries and 2 MB per file.

- Unique DOI matches are selected automatically. DOI URLs and `doi:` prefixes
  are normalized. Without a DOI match, an exact normalized title can match;
  capitalization, punctuation and whitespace differences are ignored.
- Records in the same duplicate group count as one match. Repeated entries in
  the seed file do not multiply the stopping target.
- Conflicting DOI/title information, multiple matching studies and unmatched
  titles need review. Near titles are never accepted automatically. Select a
  suggested record or search the dataset by title/author to resolve the entry.
- If a study is absent, explicitly check **I confirm this study is not present
  in this dataset**. It is retained in the import report but does not count
  toward the key-study target. If all are absent, also confirm the empty list.
- **Review matched studies** lets you inspect and correct automatic matches.
  **Clear import** removes that file's selections, retaining separately selected
  studies. Uploading another file replaces the previous imported list.

Every entry must be resolved before **Start SAFE screening** becomes available.
Importing does not insert missing articles, alter the random sample, or change
any relevance labels. When SAFE starts, the project records the source filename,
seed metadata, match decisions, manual resolutions and confirmed absences in
`safe-stopping.json`; these travel with `.asreview` exports. Keep your original
CSV/RIS file with the review materials. Import previews are not saved until
SAFE starts, so upload again if you leave or refresh the setup page.

## Corrections, restarts and concurrent tabs

- Current labels, not a cached counter, determine every stopping decision.
  Correcting a sample label updates the preliminary estimate. The original
  sample estimate and correction events remain in the project audit trail.
- Correcting a label forces a fresh ranking. If a primary label is corrected
  during the second-model phase and invalidates the original stop, screening
  pauses. **Return to ELAS u4 with a fresh counter** preserves all labels and
  requires the configured primary exclusion streak (default: 100) anew.
  Review the original decision before using it.
- If corrections remove one of the random sample's two classes, screening
  remains blocked. Resolve incorrect labels or start a new project with the
  amended sampling procedure; the program does not invent an estimate.
- SAFE serializes screening requests and shares one pending record across tabs.
  It supports one sequential screening stream per project, not independent
  simultaneous reviewers. A stale tab cannot relabel a completed record or
  submit a new decision past the stopping boundary. History corrections remain
  available through the normal history interface.
- `safe-stopping.json` in the project stores the seed, sample membership, phase
  boundaries, key studies, configured parameters, and timestamped events. ASReview's existing database
  stores decisions and correction history. Export/reimport preserves both.
  Keep using this fork when reopening a SAFE project; upstream ASReview does
  not enforce this fork's additional state file.
- Direct model changes and ordinary threshold changes are disabled for SAFE
  projects so the protocol cannot be accidentally replaced during screening.

## Install on Windows

Install Git, Python 3.12 (or 3.13), and Node.js. The integration was built and tested on Windows with Node.js 20 (matching upstream CI at the time); the original implementation used Node.js 24 on Linux.
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
CI=true npm test -- --watchAll=false --runInBand SafeStopping.test.js SeedArticle.test.js
cd ../..
.venv/bin/python -m pytest tests/test_safe_stopping.py tests/test_safe_seed_import.py asreview/webapp/tests/test_api/test_safe_stopping.py
```

The API tests exercise real primary TF-IDF/SVM training, the four-condition
conjunction, exact thresholds, sample extension, corrections, queue enforcement,
export/reimport, and phase changes. The second-model integration test substitutes
a small feature extractor for the large downloaded embedding model; it tests
the phase/ranking machinery without downloading the pretrained weights. The
full ELAS l2 model was subsequently exercised successfully on the screening computer.

Development validation used Linux, Python 3.12 and Node.js 24: 43 SAFE/matching
unit/API tests and 18 React component tests passed. The 68 core regression tests
passed during the initial SAFE implementation. The production
frontend compiled, and an independently installed wheel successfully imported
the SAFE backend and served the compiled interface. The initial cloud browser could not reach the local development server; later manual Windows tests confirmed the interface and seed exclusion dialog.


### Integration validation (November 2026)

The upstream merge and RIS corrections were validated on Windows with Python
3.12 and Node.js 20. The subsequent configurable SAFE and shutdown changes
passed targeted suites: 54 SAFE backend tests, 21 SAFE frontend tests, six
LAB/shutdown tests, and 13 RIS normalization tests (across development runs).
The user manually confirmed the compiled configurable interface and normal
Windows shutdown. Shutdown cleanup is deferred until the serving loops exit;
HTTP workers are stopped before their notification sockets are closed. Shutdown
during active model training remains to be validated.

The RIS importer normalizes slash-separated years, falls back to alternative
title and date fields, and maps URL lists to the scalar URL field. A reader-level
audit of 14,347 records found no missing source-available fields among titles,
abstracts, authors, years, primary DOIs, primary URLs and keywords; one URL was
truncated at a semicolon during parsing. Multiple DOI/URL values are not fully
represented by the scalar database schema. Retain the source bibliography.
A read-only SQLite audit of the 14,347-record project confirmed all records and seven metadata fields were preserved from reader output, with 107 harmless null-to-empty abstract conversions and zero substantive mismatches or structural integrity violations. This is separate from the known source-to-reader URL limitation.

Known limitations: the upstream App.test.js suite fails to initialize with the
react-markdown ESM dependency; this was reproduced in an unmodified upstream
worktree. Dependency security advisories require assessment before shared
deployment. The actual ELAS l2 model and visual seed highlighting were subsequently verified in disposable Windows projects. These results are not a claim of complete production
validation.


### Additional validation and GPU setup (November 2026)

CSV imports now accept UTF-8 with or without a byte-order mark. The 69 reader
tests (including dedicated RIS/CSV tests) passed, with one skipped and two
deselected. Optional grouping and Unicode changes passed 58 SAFE backend tests
before the subsequent malformed-year validation and upload-request corrections;
the user confirmed a fresh 12,340-record import with no hidden duplicates.
Final combined regression and frontend request tests remain to be run.

On the RTX 5070 Windows test machine, the CPU-only PyTorch installation was
replaced with the compatible CUDA build using the following command in the
existing virtual environment (driver 621.24):

```powershell
.\.venv\Scripts\python.exe -m pip install "torch==2.14.1+cu130" --index-url https://download.pytorch.org/whl/cu130
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -c "import torch; print(torch.__version__, torch.cuda.is_available()); print(torch.ones(10, device='cuda'))"
```

This is the tested configuration, not a universal requirement. Select a
compatible PyTorch build for other machines. Dory automatically selected
cuda:0 and completed all four embedding batches in approximately 13 seconds
on the synthetic 100-record trial. Both models and automatic secondary
stopping were exercised. Manual amber highlighting and explicit exclusion
confirmation were observed. Restart persistence and shutdown during active
training still need separate verification. Do not expose a shared instance
before reviewing dependency advisories.
