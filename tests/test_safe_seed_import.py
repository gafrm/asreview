"""Conservative bibliography matching and complete, explicit import decisions."""

import pandas as pd
import pytest

from asreview.webapp import _safe_seed_import as seeds


@pytest.fixture
def dataset():
    return pd.DataFrame(
        [
            {
                "record_id": 0,
                "group_id": 0,
                "title": "Lexical diffusion: Québec",
                "doi": "10.1234/a",
            },
            {
                "record_id": 1,
                "group_id": 0,
                "title": "Lexical diffusion — Québec",
                "doi": "https://doi.org/10.1234/A",
            },
            {
                "record_id": 2,
                "group_id": 2,
                "title": "Shared title",
                "doi": "10.1234/b",
            },
            {
                "record_id": 3,
                "group_id": 3,
                "title": "Shared title",
                "doi": "10.1234/c",
            },
            {"record_id": 4, "group_id": 4, "title": "No DOI study", "doi": None},
        ]
    )


def test_csv_bom_semicolon_quotes_and_optional_identifiers():
    entries = seeds.parse_file(
        "seeds.CSV",
        (
            "\ufeffDOI;Title;Authors;Year\n"
            'https://doi.org/10.1234/A;"A title; with punctuation";Smith;2020\n'
            ";Title only;;\n10.1234/b;;;\n\n"
        ).encode(),
    )
    assert len(entries) == 3
    assert entries[0]["title"] == "A title; with punctuation"
    assert entries[1]["doi"] == ""
    assert entries[2]["title"] == ""


def test_ris_uses_bibliography_but_ignores_embedded_labels():
    raw = (
        b"TY  - JOUR\nTI  - A title\nDO  - 10.1234/a\nAU  - Smith\n"
        b"PY  - 2020\nN1  - ASReview_relevant\nER  - \n"
    )
    assert seeds.parse_file("seeds.ris", raw) == [
        {"title": "A title", "doi": "10.1234/a", "authors": "Smith", "year": "2020"}
    ]


@pytest.mark.parametrize(
    "filename,raw",
    [
        ("seeds.csv", b"filename\npaper.pdf\n"),
        ("seeds.csv", b"title\n"),
        ("seeds.csv", b"doi,title\ninvalid,Paper\n"),
        ("seeds.csv", b"doi,title,year\n,,2020\n"),
        ("seeds.csv", b"title,Title\nOne,Two\n"),
        ("seeds.csv", b"title,doi\nUnquoted, comma,10.1234/a\n"),
        ("seeds.ris", b"TY  - JOUR\nTI  - Truncated\n"),
        ("seeds.pdf", b"not a bibliography"),
        ("seeds.csv", b"title\n" + b"x" * seeds.MAX_BYTES),
        ("seeds.csv", b"title\n" + b"Paper\n" * (seeds.MAX_ENTRIES + 1)),
    ],
)
def test_bad_files_are_not_silently_partially_imported(filename, raw):
    with pytest.raises(ValueError):
        seeds.parse_file(filename, raw)


def test_exact_matching_duplicate_groups_conflicts_and_missing(dataset):
    rows = seeds.match_entries(
        [
            {"doi": "DOI: https://dx.doi.org/10.1234%2FA"},
            {"title": "LEXICAL   DIFFUSION — Québec!"},
            {"title": "Shared title"},
            {"title": "Shared title", "doi": "10.1234/a"},
            {"title": "Shared title", "doi": "10.1234/d"},
            {"title": "No DOI study", "doi": "10.1234/new"},
            {"title": "No DOI studies"},
        ],
        dataset,
    )
    assert [row["status"] for row in rows] == [
        "matched",
        "matched",
        "ambiguous",
        "conflict",
        "conflict",
        "matched",
        "missing",
    ]
    assert rows[0]["match"]["record_id"] == rows[1]["match"]["record_id"] == 0
    assert rows[0]["candidate_count"] == 1
    assert rows[5]["method"] == "title"
    assert rows[6]["match"] is None  # A near title is never automatically accepted.


def test_audit_preserves_absence_and_manual_resolution(dataset):
    report = seeds.import_audit(
        {
            "filename": "C:\\lists\\seeds.csv",
            "entries": [
                {"doi": "10.1234/a", "record_id": 1},
                {"title": "Shared title", "record_id": 3},
                {"title": "Missing", "record_id": None, "not_present": True},
            ],
        },
        dataset,
        [0, 3],
    )
    assert report["filename"] == "seeds.csv"
    assert [row["resolution"] for row in report["entries"]] == [
        "doi",
        "manual",
        "not_present",
    ]
    assert report["entries"][0]["group_id"] == 0


@pytest.mark.parametrize(
    "resolution",
    [
        {},
        {"record_id": 999},
        {"record_id": True},
        {"record_id": 0, "not_present": True},
        {"record_id": 2},
    ],
)
def test_audit_rejects_unresolved_or_unselected_records(dataset, resolution):
    with pytest.raises(ValueError):
        seeds.import_audit(
            {"entries": [{"title": "Paper", **resolution}]}, dataset, [0]
        )
