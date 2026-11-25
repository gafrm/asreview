import pytest

from asreview.data.tabular import CSVReader


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig"])
def test_csv_title_preserved_with_or_without_bom(encoding, tmp_path):
    path = tmp_path / "dataset.csv"
    path.write_text(
        "title,abstract,doi,year\n"
        "Lexical innovation,Study of new words,10.99999/test,2021\n",
        encoding=encoding,
    )

    records = CSVReader.read_records(path, dataset_id="test")

    assert len(records) == 1
    assert records[0].title == "Lexical innovation"
    assert records[0].abstract == "Study of new words"
    assert records[0].doi == "10.99999/test"
    assert records[0].year == 2021
