"""Shared fixtures: a tiny hand-built dataset and a small generated one."""

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture
def registry():
    """Four firms: A and B share a director; C and D are unrelated."""
    return pd.DataFrame({
        "firm_id": ["A", "B", "C", "D"],
        "registered_name": ["Alpha Builders Corp.", "Beta Construction Inc.",
                            "Gamma Engineering Co.", "Delta Civil Works Enterprises"],
        "region": ["NCR"] * 4,
        "address": ["1 Rizal St., Pasig", "2 Luna St., Pasig",
                    "3 Mabini Ave., Makati", "4 Burgos St., Taguig"],
        "directors": ["Jose A. Santos; Ana B. Cruz", "Jose A. Santos",
                      "Ramon C. Reyes", "Liza D. Tan"],
    })


@pytest.fixture
def ring_bids():
    """Twelve tenders. A and B always bid together, a minute apart, and take
    turns winning. C and D bid on random tenders hours apart and lose."""
    rows = []
    for t in range(12):
        ocid = f"T{t:02d}"
        close = pd.Timestamp("2024-01-01 10:00") + pd.Timedelta(days=t)
        winner = "A" if t % 2 == 0 else "B"
        bidders = [("A", "Alpha Builders Corp."), ("B", "BETA CONSTRUCTION INC")]
        if t % 3 == 0:
            bidders.append(("C", "Gamma Engineering Co."))
        if t % 4 == 0:
            bidders.append(("D", "Delta Civil Works Enterprises"))
        for i, (fid, name) in enumerate(bidders):
            win = fid == winner
            rows.append({
                "ocid": ocid, "office_id": "O1" if t < 8 else "O2",
                "office_name": "Office One" if t < 8 else "Office Two", "region": "NCR",
                "tender_close": close, "estimated_value": 1_000_000.0,
                "bidder_name": name,
                "bid_amount": 950_000.0 if win else 1_000_000.0 + i * 10_000,
                "submitted_at": close - pd.Timedelta(minutes=30 - i if fid in "AB" else 300 * i),
                "is_winner": int(win),
            })
    return pd.DataFrame(rows)


@pytest.fixture(scope="session")
def small_synthetic(tmp_path_factory):
    """A small generated dataset written to disk, shared across tests."""
    import generate_data
    out = tmp_path_factory.mktemp("synth")
    d = generate_data.generate(seed=3, n_tenders=1500, n_firms=150, n_offices=12)
    import json
    (out / "synthetic_tenders_ocds.json").write_text(json.dumps({"releases": d["releases"]}))
    generate_data.write_csv(out / "synthetic_bids.csv", d["bids"])
    generate_data.write_csv(out / "synthetic_registry.csv", d["registry"])
    generate_data.write_csv(out / "synthetic_ground_truth_rings.csv", d["truth"])
    generate_data.write_csv(out / "synthetic_ground_truth_names.csv", d["name_truth"])
    generate_data.write_csv(out / "synthetic_ground_truth_offices.csv", d["ring_offices"])
    return out
