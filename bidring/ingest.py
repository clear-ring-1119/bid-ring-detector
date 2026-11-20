"""Load OCDS-style releases or a flat bids CSV into a tidy bids table.

The output is one row per bid with these columns::

    ocid, office_id, office_name, region, tender_close, estimated_value,
    bidder_name, bid_amount, submitted_at, is_winner

The table can be saved to SQLite for inspection. For production volumes
(hundreds of thousands of contracts, several years) use Postgres instead;
the schema is the same.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd

BID_COLUMNS = ["ocid", "office_id", "office_name", "region", "tender_close",
               "estimated_value", "bidder_name", "bid_amount", "submitted_at",
               "is_winner"]


def load_ocds_json(path: str | Path) -> pd.DataFrame:
    """Flatten OCDS-style releases into the bids table.

    Expects ``{"releases": [...]}`` or a bare list. A bid is the winner if
    its tenderer name equals an active award supplier name.
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    releases = raw["releases"] if isinstance(raw, dict) else raw
    rows = []
    for r in releases:
        buyer = r.get("buyer", {})
        tender = r.get("tender", {})
        winners = {s.get("name") for a in r.get("awards", [])
                   if a.get("status", "active") == "active"
                   for s in a.get("suppliers", [])}
        for b in r.get("bids", {}).get("details", []):
            for t in b.get("tenderers", []):
                rows.append({
                    "ocid": r["ocid"],
                    "office_id": buyer.get("id"),
                    "office_name": buyer.get("name"),
                    "region": buyer.get("region"),
                    "tender_close": tender.get("tenderPeriod", {}).get("endDate"),
                    "estimated_value": tender.get("value", {}).get("amount"),
                    "bidder_name": t.get("name"),
                    "bid_amount": b.get("value", {}).get("amount"),
                    "submitted_at": b.get("date"),
                    "is_winner": int(t.get("name") in winners),
                })
    return _clean(pd.DataFrame(rows, columns=BID_COLUMNS))


def load_bids_csv(path: str | Path) -> pd.DataFrame:
    """Load a flat bids CSV with the columns in ``BID_COLUMNS``."""
    df = pd.read_csv(path)
    missing = set(BID_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"Bids CSV is missing columns: {sorted(missing)}")
    return _clean(df[BID_COLUMNS])


def load(path: str | Path) -> pd.DataFrame:
    """Load by file extension: ``.json`` for OCDS, ``.csv`` for flat bids."""
    p = Path(path)
    if p.suffix.lower() == ".json":
        return load_ocds_json(p)
    if p.suffix.lower() == ".csv":
        return load_bids_csv(p)
    raise ValueError(f"Unsupported file type: {p.suffix}")


def load_registry(path: str | Path) -> pd.DataFrame:
    """Load the corporate registry (firm_id, registered_name, address, directors)."""
    df = pd.read_csv(path, dtype=str).fillna("")
    for col in ("firm_id", "registered_name", "address", "directors"):
        if col not in df.columns:
            raise ValueError(f"Registry is missing column: {col}")
    return df


def to_sqlite(df: pd.DataFrame, db_path: str | Path, table: str = "bids") -> None:
    """Write a table to SQLite, replacing any existing table of that name."""
    with sqlite3.connect(db_path) as con:
        df.to_sql(table, con, if_exists="replace", index=False)


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    """Parse types and drop rows with no bidder name."""
    df = df.copy()
    df["submitted_at"] = pd.to_datetime(df["submitted_at"], errors="coerce")
    df["tender_close"] = pd.to_datetime(df["tender_close"], errors="coerce")
    df["bid_amount"] = pd.to_numeric(df["bid_amount"], errors="coerce")
    df["estimated_value"] = pd.to_numeric(df["estimated_value"], errors="coerce")
    df["is_winner"] = df["is_winner"].fillna(0).astype(int)
    df = df[df["bidder_name"].notna() & (df["bidder_name"].astype(str).str.strip() != "")]
    return df.reset_index(drop=True)
