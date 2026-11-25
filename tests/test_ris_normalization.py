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
