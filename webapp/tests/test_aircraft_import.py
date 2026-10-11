"""Aircraft source validation and idempotent model updates."""

import duckdb
import pytest

from webapp.data.import_aircraft import (
    CREATE_AIRCRAFT_SQL,
    aircraft_upsert_sql,
    read_aircraft_csv,
)


def test_source_duplicates_and_leading_zero_ids(tmp_path):
    source = tmp_path / "aircraft.csv"
    source.write_text(
        "aircraft_id,aircraft_family,aircraft_type,all_installed_flag\n"
        "04150,A320,A320-200,YES\n04150,A320,A320-200,NO\n"
        "17000037,EMBRAER RJ,ERJ170,YES\n"
    )
    rows = read_aircraft_csv(source)
    assert rows == [("04150", "A320", "A320-200"), ("17000037", "EMBRAER RJ", "ERJ170")]
    with duckdb.connect() as db:
        db.execute(CREATE_AIRCRAFT_SQL)
        db.execute(aircraft_upsert_sql(rows))
        db.execute(aircraft_upsert_sql(rows))
        assert db.execute("SELECT count(*) FROM aircraft").fetchone()[0] == 2
        db.execute(aircraft_upsert_sql([("04150", "A320", "A321-200")]))
        assert (
            db.execute(
                "SELECT aircraft_type FROM aircraft WHERE aircraft_id='04150'"
            ).fetchone()[0]
            == "A321-200"
        )


@pytest.mark.parametrize(
    "content",
    [
        "aircraft_id,aircraft_family,aircraft_type\n1,A320,A320-200\n00001,A320,A321-200\n",
        "aircraft_id,aircraft_family,aircraft_type\n1,A320,\n",
        "aircraft_id,aircraft_family,aircraft_type\n",
        "aircraft_id,aircraft_family\n1,A320\n",
    ],
)
def test_invalid_source_is_rejected_before_import(tmp_path, content):
    source = tmp_path / "aircraft.csv"
    source.write_text(content)
    with pytest.raises(ValueError):
        read_aircraft_csv(source)
