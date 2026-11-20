import pandas as pd

from bidring import resolve


def test_normalise_standardises_case_punctuation_and_forms():
    assert resolve.normalise("Alpha Builders Corporation") == "ALPHA BUILDERS CORP"
    assert resolve.normalise("ALPHA BUILDERS CORP.") == "ALPHA BUILDERS CORP"
    assert resolve.normalise("Alpha Construction & Supply") == "ALPHA CONSTRUCTION AND SUPPLY"


def test_legal_form_keeps_sister_firms_apart(registry):
    reg = registry.copy()
    reg.loc[len(reg)] = ["E", "Alpha Builders Inc.", "NCR", "x", "y"]
    exact, blocks = resolve.build_index(reg)
    assert resolve.match_name("Alpha Builders Corp", exact, blocks)[0] == "A"
    assert resolve.match_name("ALPHA BUILDERS INC.", exact, blocks)[0] == "E"


def test_fuzzy_match_handles_typos(registry):
    exact, blocks = resolve.build_index(registry)
    fid, score = resolve.match_name("Alpha Bulider sCorp.", exact, blocks, 0.85)
    assert fid == "A" and 0.85 <= score < 1.0


def test_unknown_name_is_unresolved(registry):
    exact, blocks = resolve.build_index(registry)
    fid, score = resolve.match_name("Zeta Holdings", exact, blocks)
    assert fid.startswith("UNRESOLVED:") and score == 0.0


def test_resolve_bids_dedupes_firm_within_tender(registry, ring_bids):
    dup = ring_bids.iloc[[0]].copy()
    dup["bidder_name"] = "ALPHA BUILDERS CORPORATION"
    bids = pd.concat([ring_bids, dup])
    out, name_map = resolve.resolve_bids(bids, registry)
    assert not out.duplicated(["ocid", "firm_id"]).any()
    assert set(out["firm_id"]) == {"A", "B", "C", "D"}
    assert {"bidder_name", "firm_id", "match_score"} <= set(name_map.columns)
