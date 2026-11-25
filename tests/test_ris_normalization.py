import pytest

from asreview.data.ris import RISReader


@pytest.mark.parametrize(
    "date",
    ["2021", "2021///", "2021/06//", "2021/06/15/"],
)
def test_ris_publication_year(date, tmp_path):
    path = tmp_path / "test.ris"
    path.write_text(
        f"TY  - JOUR\nTI  - Example article\nPY  - {date}\nER  - \n",
        encoding="utf-8",
    )

    records = RISReader.read_records(path, dataset_id="test")

    assert len(records) == 1
    assert records[0].year == 2021
    assert records[0].title == "Example article"


def test_mixed_ris_title_fields(tmp_path):
    path = tmp_path / "mixed.ris"
    path.write_text(
        "TY  - JOUR\nTI  - First article\nER  - \n\n"
        "TY  - JOUR\nT1  - Second article\nER  - \n\n"
        "TY  - JOUR\nTI  - Preferred title\n"
        "T1  - Alternative title\nER  - \n",
        encoding="utf-8",
    )

    records = RISReader.read_records(path, dataset_id="test")

    assert len(records) == 3
    assert [r.title for r in records] == [
        "First article",
        "Second article",
        "Preferred title",
    ]


def test_ris_primary_title_only(tmp_path):
    path = tmp_path / "primary.ris"
    path.write_text(
        "TY  - JOUR\nT1  - Example article\nER  - \n",
        encoding="utf-8",
    )

    records = RISReader.read_records(path, dataset_id="test")

    assert len(records) == 1
    assert records[0].title == "Example article"


@pytest.mark.parametrize(
    "tag,date,expected",
    [
        ("PY", "2021///", 2021),
        ("Y1", "2022/06/15/", 2022),
        ("DA", "2023-04-12", 2023),
        ("DA", "0001-01-01", None),
    ],
)
def test_ris_alternative_year_fields(tag, date, expected, tmp_path):
    path = tmp_path / "date.ris"
    path.write_text(
        f"TY  - JOUR\nTI  - Article\n{tag}  - {date}\nER  - \n",
        encoding="utf-8",
    )
    records = RISReader.read_records(path, dataset_id="test")
    assert records[0].year == expected


def test_ris_year_field_priority(tmp_path):
    path = tmp_path / "dates.ris"
    path.write_text(
        "TY  - JOUR\nTI  - Article\n"
        "PY  - 2021\nY1  - 2022///\nDA  - 2023-01-01\nER  - \n",
        encoding="utf-8",
    )
    records = RISReader.read_records(path, dataset_id="test")
    assert records[0].year == 2021


def test_ris_url_import(tmp_path):
    path = tmp_path / "urls.ris"
    path.write_text(
        "TY  - JOUR\nTI  - Article\n"
        "UR  - https://example.org/article\nER  - \n",
        encoding="utf-8",
    )
    records = RISReader.read_records(path, dataset_id="test")
    assert records[0].url == "https://example.org/article"


def test_ris_multiple_urls(tmp_path):
    path = tmp_path / "multiple.ris"
    path.write_text(
        "TY  - JOUR\nTI  - Article\n"
        "UR  - https://example.org/first\n"
        "UR  - https://example.org/second\nER  - \n",
        encoding="utf-8",
    )
    records = RISReader.read_records(path, dataset_id="test")
    assert records[0].url == "https://example.org/first"
