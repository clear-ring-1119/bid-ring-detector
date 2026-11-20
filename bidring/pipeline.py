"""Run the whole pipeline: ingest, resolve, graph, score, test, rank, report.

Usage::

    python -m bidring.pipeline --bids data/proto_tenders_ocds.json \\
        --registry data/proto_registry.csv --out output [--config my.json]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from . import graph as graph_mod
from . import ingest, offices, recurrent, report, resolve, scoring
from .config import Config


def run(bids: pd.DataFrame, registry: pd.DataFrame, cfg: Config | None = None) -> dict:
    """Run every analysis step in memory and return the results."""
    cfg = cfg or Config()
    resolved, name_map = resolve.resolve_bids(bids, registry, cfg.fuzzy_threshold)
    g = graph_mod.build_cobid_graph(resolved, cfg.min_cobids)
    scored = scoring.score_pairs(resolved, g, registry, cfg)
    flagged = scoring.flag(scored, cfg)
    rings = graph_mod.candidate_rings(flagged)
    rel = recurrent.recurrent_relationships(resolved, g, cfg.min_cobids, cfg.recurrent_alpha)
    kcore = recurrent.max_kcore(recurrent.directed_graph(rel))
    office_table = offices.office_risk(resolved, flagged, relationships=rel, kcore=kcore)
    return {
        "bids": resolved, "name_map": name_map, "graph": g, "scored": scored,
        "flagged": flagged, "rings": rings, "offices": office_table,
        "relationships": rel, "kcore": kcore,
        "config": cfg.to_dict(),
        "summary": {
            "n_tenders": int(resolved["ocid"].nunique()),
            "n_bids": int(len(resolved)),
            "n_firms": int(resolved["firm_id"].nunique()),
            "n_unresolved_names": int(name_map["firm_id"].str.startswith("UNRESOLVED").sum()),
            "n_pairs_scored": int(len(scored)),
            "n_flagged": int(len(flagged)),
            "n_rings": int(rings["ring_id"].nunique()) if not rings.empty else 0,
            "n_relationships": int(rel["significant"].sum()) if not rel.empty else 0,
        },
    }


def main(argv: list[str] | None = None) -> dict:
    """Command-line entry point."""
    ap = argparse.ArgumentParser(description="Screen procurement data for likely bid rings.")
    ap.add_argument("--bids", required=True, help="OCDS-style .json or flat bids .csv")
    ap.add_argument("--registry", required=True, help="corporate registry .csv")
    ap.add_argument("--out", default="output")
    ap.add_argument("--config", help="JSON file of threshold overrides")
    ap.add_argument("--sqlite", help="also save the resolved bids to this SQLite file")
    a = ap.parse_args(argv)

    cfg = Config.from_json(a.config) if a.config else Config()
    bids = ingest.load(a.bids)
    registry = ingest.load_registry(a.registry)
    result = run(bids, registry, cfg)
    if "synthetic" in Path(a.bids).name.lower():
        result["data_note"] = "Input data is SYNTHETIC (generated for testing)."
    if a.sqlite:
        ingest.to_sqlite(result["bids"], a.sqlite)
    names = dict(zip(registry["firm_id"], registry["registered_name"]))
    path = report.write_outputs(a.out, result, names)
    s = result["summary"]
    print(f"Scored {s['n_pairs_scored']} pairs; flagged {s['n_flagged']}; "
          f"{s['n_rings']} candidate rings; {s['n_relationships']} recurrent "
          f"loser->winner links. Report: {path}")
    return result


if __name__ == "__main__":
    main()
