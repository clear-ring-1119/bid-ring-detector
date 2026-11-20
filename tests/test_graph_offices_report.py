import pandas as pd

from bidring import graph, offices, report, resolve
from bidring.config import Config
from bidring.pipeline import run


def test_graph_edges_and_node_stats(registry, ring_bids):
    bids, _ = resolve.resolve_bids(ring_bids, registry)
    g = graph.build_cobid_graph(bids, 1)
    assert g["A"]["B"]["n"] == 12
    assert g.nodes["A"]["n_wins"] == 6 and g.nodes["C"]["n_wins"] == 0


def test_candidate_rings_groups_components():
    fp = pd.DataFrame({"firm_a": ["A", "B", "X"], "firm_b": ["B", "C", "Y"],
                       "score": [0.9, 0.6, 0.7]})
    r = graph.candidate_rings(fp)
    groups = r.groupby("ring_id")["firm_id"].apply(set).to_dict()
    assert groups == {"C01": {"A", "B", "C"}, "C02": {"X", "Y"}}
    assert graph.candidate_rings(fp.iloc[0:0]).empty


def test_office_risk_ranks_exposed_office(registry, ring_bids):
    bids, _ = resolve.resolve_bids(ring_bids, registry)
    flagged = pd.DataFrame({"firm_a": ["A"], "firm_b": ["B"], "score": [0.9]})
    o = offices.office_risk(bids, flagged, min_tenders=5)
    assert list(o["rank"]) == [1, 2]
    assert (o["flagged_share"] == 1.0).all()
    assert o.set_index("office_id").loc["O2", "low_volume"]
    empty = offices.office_risk(bids, flagged.iloc[0:0])
    assert (empty["n_flagged"] == 0).all()


def test_evidence_pack_and_report(tmp_path, registry, ring_bids):
    res = run(ring_bids, registry, Config(min_cobids=3))
    row = res["flagged"].iloc[0]
    ev = report.evidence_pack(res["bids"], row)
    assert ev["ocid"].nunique() == 12
    assert (ev.loc[ev.is_winner == 1, "pct_of_winning_bid"] == 100.0).all()
    names = dict(zip(registry.firm_id, registry.registered_name))
    res["data_note"] = "Test data <synthetic>."
    path = report.write_outputs(tmp_path, res, names)
    text = path.read_text()
    assert "Bid-ring screening report" in text and "&lt;synthetic&gt;" in text
    assert (tmp_path / "evidence" / "A__B.csv").exists()
    for f in ("flagged_pairs.csv", "candidate_rings.csv", "office_risk.csv",
              "name_resolution.csv", "config_used.json", "all_scored_pairs.csv"):
        assert (tmp_path / f).exists()
