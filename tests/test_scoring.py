import json

import pytest

from bidring import graph, resolve, scoring
from bidring.config import Config


@pytest.fixture
def scored(registry, ring_bids):
    cfg = Config(min_cobids=3)
    bids, _ = resolve.resolve_bids(ring_bids, registry)
    g = graph.build_cobid_graph(bids, cfg.min_cobids)
    return scoring.score_pairs(bids, g, registry, cfg), cfg


def test_ring_pair_scores_highest(scored):
    df, _ = scored
    top = df.iloc[0]
    assert (top.firm_a, top.firm_b) == ("A", "B")
    assert top.overlap == round(12 / (12 + 8), 3)  # shrunk by overlap_prior
    assert top.behaviour == 1.0 and top.timing == 1.0
    assert top.registry == 1.0 and "JOSE A. SANTOS" in top.shared_directors
    assert top.rotation == 1.0  # both took turns


def test_honest_pair_not_flagged(scored):
    df, cfg = scored
    flagged = scoring.flag(df, cfg)
    pairs = set(zip(flagged.firm_a, flagged.firm_b))
    assert ("A", "B") in pairs
    assert ("C", "D") not in pairs


def test_cover_bidder_detected(scored):
    df, _ = scored
    cd = df[(df.firm_a == "A") & (df.firm_b == "C")].iloc[0]
    assert cd.cover_bidder == "C"  # C never wins


def test_shared_address_scores_075(registry, ring_bids):
    reg = registry.copy()
    reg["directors"] = ["P1", "P2", "P3", "P4"]
    reg.loc[reg.firm_id == "B", "address"] = "1 rizal st.,  pasig".upper()
    cfg = Config(min_cobids=3)
    bids, _ = resolve.resolve_bids(ring_bids, reg)
    g = graph.build_cobid_graph(bids, 3)
    df = scoring.score_pairs(bids, g, reg, cfg)
    assert df.iloc[0].registry == 0.75


def test_min_cobids_filters(registry, ring_bids):
    bids, _ = resolve.resolve_bids(ring_bids, registry)
    g = graph.build_cobid_graph(bids, 1)
    df = scoring.score_pairs(bids, g, registry, Config(min_cobids=100))
    assert df.empty


def test_weights_normalise_and_validate(tmp_path):
    w = Config(w_overlap=2, w_behaviour=2, w_timing=0, w_registry=0).weights()
    assert w == {"overlap": 0.5, "behaviour": 0.5, "timing": 0.0, "registry": 0.0}
    with pytest.raises(ValueError):
        Config(w_overlap=0, w_behaviour=0, w_timing=0, w_registry=0).weights()
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"flag_threshold": 0.7}))
    assert Config.from_json(p).flag_threshold == 0.7
    p.write_text(json.dumps({"nonsense": 1}))
    with pytest.raises(ValueError):
        Config.from_json(p)


def test_overlap_prior_shrinks_small_firms(registry, ring_bids):
    bids, _ = resolve.resolve_bids(ring_bids, registry)
    g = graph.build_cobid_graph(bids, 3)
    raw = scoring.score_pairs(bids, g, registry, Config(min_cobids=3, overlap_prior=0))
    shrunk = scoring.score_pairs(bids, g, registry, Config(min_cobids=3, overlap_prior=8))
    assert raw.iloc[0].overlap == 1.0
    assert shrunk.iloc[0].overlap < raw.iloc[0].overlap
