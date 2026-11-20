"""Generator, CLI and validation on a small synthetic dataset."""

import generate_data
import validate
from bidring import pipeline


def test_generator_is_deterministic_and_labelled():
    a = generate_data.generate(seed=5, n_tenders=300, n_firms=120, n_offices=8)
    b = generate_data.generate(seed=5, n_tenders=300, n_firms=120, n_offices=8)
    assert a["bids"] == b["bids"]
    assert len(a["releases"]) == 300
    assert all(r["ocid"].startswith("ocds-synthetic-") for r in a["releases"])
    assert all(r["tender"]["title"].startswith("Synthetic") for r in a["releases"])
    sizes = {}
    for t in a["truth"]:
        sizes[t["ring_id"]] = sizes.get(t["ring_id"], 0) + 1
    assert sizes == {"R1": 4, "R2": 3, "R3": 5, "R4": 3}


def test_planted_rings_recovered(small_synthetic):
    r = validate.validate(small_synthetic)
    assert r["names"]["accuracy"] > 0.98
    assert r["pairs"]["recall"] >= 0.8
    assert r["pairs"]["precision"] >= 0.6
    assert sum(x["jaccard"] >= 0.75 for x in r["rings"]) >= 3
    assert r["offices"]["share"] >= 0.5
    assert "R2" in r["recurrent"]["rings_with_links"]


def test_cli_writes_report(small_synthetic, tmp_path):
    out = tmp_path / "out"
    res = pipeline.main(["--bids", str(small_synthetic / "synthetic_bids.csv"),
                         "--registry", str(small_synthetic / "synthetic_registry.csv"),
                         "--out", str(out), "--sqlite", str(tmp_path / "b.sqlite")])
    assert (out / "report.html").exists()
    assert "SYNTHETIC" in (out / "report.html").read_text()
    assert res["summary"]["n_flagged"] > 0
    assert (tmp_path / "b.sqlite").exists()


def test_cli_with_config_file(small_synthetic, tmp_path):
    cfg = tmp_path / "c.json"
    cfg.write_text('{"flag_threshold": 0.99}')
    res = pipeline.main(["--bids", str(small_synthetic / "synthetic_tenders_ocds.json"),
                         "--registry", str(small_synthetic / "synthetic_registry.csv"),
                         "--out", str(tmp_path / "o"), "--config", str(cfg)])
    assert res["config"]["flag_threshold"] == 0.99
    assert res["summary"]["n_flagged"] == 0
    assert (tmp_path / "o" / "report.html").exists()
