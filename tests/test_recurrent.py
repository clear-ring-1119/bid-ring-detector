import pandas as pd
import pytest

from bidring import graph, recurrent, resolve


def test_binom_sf_matches_known_values():
    assert recurrent.binom_sf(0, 5, 0.3) == 1.0
    assert recurrent.binom_sf(5, 5, 0.5) == pytest.approx(1 / 32)
    assert recurrent.binom_sf(1, 3, 0.5) == pytest.approx(7 / 8)


def test_bh_adjust_monotone_and_capped():
    q = recurrent.bh_adjust([0.01, 0.04, 0.03, 0.5])
    assert q == pytest.approx([0.04, 0.16 / 3, 0.16 / 3, 0.5])


def _cover_bids():
    """W always wins when L bids (20 tenders); W wins 1 in 5 elsewhere."""
    rows = []
    for t in range(20):
        for f, win in (("W", 1), ("L", 0)):
            rows.append({"ocid": f"S{t}", "firm_id": f, "is_winner": win})
    for t in range(40):
        rows.append({"ocid": f"E{t}", "firm_id": "W", "is_winner": int(t % 5 == 0)})
        rows.append({"ocid": f"E{t}", "firm_id": f"X{t}", "is_winner": int(t % 5 != 0)})
    return pd.DataFrame(rows)


def test_cover_relationship_is_significant():
    bids = _cover_bids()
    g = graph.build_cobid_graph(bids, 8)
    rel = recurrent.recurrent_relationships(bids, g, min_cobids=8, alpha=0.01)
    top = rel.iloc[0]
    assert (top.loser, top.winner) == ("L", "W") and top.significant
    assert not rel[(rel.loser == "W") & (rel.winner == "L")]["significant"].any()
    dg = recurrent.directed_graph(rel)
    assert list(dg.edges()) == [("L", "W")]
    assert recurrent.max_kcore(dg) == {"L": 1, "W": 1}


def test_no_edges_gives_empty_table(registry, ring_bids):
    bids, _ = resolve.resolve_bids(ring_bids, registry)
    g = graph.build_cobid_graph(bids, 100)
    rel = recurrent.recurrent_relationships(bids, g, min_cobids=100)
    assert rel.empty and "significant" in rel.columns
    assert recurrent.max_kcore(recurrent.directed_graph(rel)) == {}
