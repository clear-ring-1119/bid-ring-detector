import json

import pandas as pd
import pytest

from bidring import ingest


def test_load_ocds_json_flattens_bids_and_winner(tmp_path):
    rel = {"releases": [{
        "ocid": "X1", "buyer": {"id": "O1", "name": "Office", "region": "NCR"},
        "tender": {"value": {"amount": 100}, "tenderPeriod": {"endDate": "2024-01-01T10:00"}},
        "bids": {"details": [
            {"date": "2024-01-01T09:00", "tenderers": [{"name": "A Co."}], "value": {"amount": 90}},
            {"date": "2024-01-01T09:05", "tenderers": [{"name": "B Co."}], "value": {"amount": 95}},
        ]},
        "awards": [{"status": "active", "suppliers": [{"name": "A Co."}]}],
    }]}
    p = tmp_path / "r.json"
    p.write_text(json.dumps(rel))
    df = ingest.load(p)
    assert list(df.columns) == ingest.BID_COLUMNS
    assert len(df) == 2
    assert df.set_index("bidder_name")["is_winner"].to_dict() == {"A Co.": 1, "B Co.": 0}
    assert pd.api.types.is_datetime64_any_dtype(df["submitted_at"])


def test_csv_and_json_give_same_rows(small_synthetic):
    a = ingest.load(small_synthetic / "proto_tenders_ocds.json")
    b = ingest.load(small_synthetic / "proto_bids.csv")
    assert len(a) == len(b)
    assert a["is_winner"].sum() == b["is_winner"].sum()


def test_missing_columns_raise(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("ocid,bidder_name\nX,A\n")
    with pytest.raises(ValueError):
        ingest.load(p)


def test_unsupported_extension(tmp_path):
    with pytest.raises(ValueError):
        ingest.load(tmp_path / "x.parquet")


def test_sqlite_roundtrip(tmp_path, ring_bids):
    import sqlite3
    db = tmp_path / "b.sqlite"
    ingest.to_sqlite(ring_bids, db)
    with sqlite3.connect(db) as con:
        n = con.execute("select count(*) from bids").fetchone()[0]
    assert n == len(ring_bids)
