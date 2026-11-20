"""Check the detector against the planted rings in the SYNTHETIC data.

Reports three things:

1. Name resolution accuracy (typed names vs the true firm IDs).
2. Pair-level precision and recall. A true pair is any two firms in the
   same planted ring.
3. Ring-level recovery: for each planted ring, the best-matching candidate
   ring and their Jaccard overlap.
4. Office ranking: how many ring offices land at the top.
5. The directed recurrent-loser test: how many links fall inside rings.

These numbers only show the code finds what the generator planted. They
say nothing about performance on real procurement data.

Usage::

    python validate.py [--data data] [--config my.json] [--json out.json]
"""

from __future__ import annotations

import argparse
import json
from itertools import combinations
from pathlib import Path

import pandas as pd

from bidring import ingest
from bidring.config import Config
from bidring.pipeline import run


def true_pairs(truth: pd.DataFrame) -> set[tuple[str, str]]:
    """All within-ring firm pairs from the ground-truth table."""
    pairs = set()
    for _, g in truth.groupby("ring_id"):
        pairs |= {tuple(sorted(p)) for p in combinations(g["firm_id"], 2)}
    return pairs


def pair_metrics(flagged: pd.DataFrame, truth_pairs: set) -> dict:
    """Precision, recall and F1 of flagged pairs against true pairs."""
    pred = {tuple(sorted(p)) for p in zip(flagged["firm_a"], flagged["firm_b"])}
    tp = len(pred & truth_pairs)
    precision = tp / len(pred) if pred else 0.0
    recall = tp / len(truth_pairs) if truth_pairs else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"flagged": len(pred), "true_pairs": len(truth_pairs), "true_positives": tp,
            "false_positives": len(pred - truth_pairs),
            "missed": sorted(map(list, truth_pairs - pred)),
            "precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3)}


def ring_recovery(rings: pd.DataFrame, truth: pd.DataFrame) -> list[dict]:
    """Best Jaccard match between each planted ring and the candidate rings."""
    cands = {r: set(g["firm_id"]) for r, g in rings.groupby("ring_id")} if not rings.empty else {}
    out = []
    for rid, g in truth.groupby("ring_id"):
        planted = set(g["firm_id"])
        best_id, best = None, 0.0
        for cid, members in cands.items():
            j = len(planted & members) / len(planted | members)
            if j > best:
                best_id, best = cid, j
        out.append({"planted_ring": rid, "size": len(planted),
                    "best_candidate": best_id, "jaccard": round(best, 3)})
    return out


def name_accuracy(name_map: pd.DataFrame, name_truth: pd.DataFrame) -> dict:
    """Share of distinct typed names resolved to the right firm."""
    m = name_map.merge(name_truth, on="bidder_name", suffixes=("_pred", "_true"))
    correct = int((m["firm_id_pred"] == m["firm_id_true"]).sum())
    unresolved = int(m["firm_id_pred"].str.startswith("UNRESOLVED").sum())
    return {"names": len(m), "correct": correct,
            "wrong_firm": len(m) - correct - unresolved, "unresolved": unresolved,
            "accuracy": round(correct / len(m), 4) if len(m) else 0.0}


def threshold_sweep(scored: pd.DataFrame, truth_pairs: set,
                    thresholds=(0.4, 0.45, 0.5, 0.55, 0.6, 0.7)) -> list[dict]:
    """Precision and recall at several flag thresholds, from one scoring run."""
    out = []
    for t in thresholds:
        m = pair_metrics(scored[scored["score"] >= t], truth_pairs)
        out.append({"threshold": t, "flagged": m["flagged"],
                    "precision": m["precision"], "recall": m["recall"]})
    return out


def office_recovery(office_table: pd.DataFrame, ring_offices: pd.DataFrame) -> dict:
    """How many planted ring offices appear in the top-k of the office ranking,
    with k equal to the number of planted ring offices."""
    planted = set(ring_offices["office_id"])
    k = len(planted)
    top = set(office_table.head(k)["office_id"])
    return {"planted_offices": k, "in_top_k": len(planted & top),
            "share": round(len(planted & top) / k, 3) if k else 0.0}


def recurrent_check(rel: pd.DataFrame, truth: pd.DataFrame) -> dict:
    """Significant loser -> winner links, split by whether both firms share a planted ring."""
    ring_of = dict(zip(truth["firm_id"], truth["ring_id"]))
    sig = rel[rel["significant"]] if not rel.empty else rel
    inside = [(a, b) for a, b in zip(sig["loser"], sig["winner"])
              if ring_of.get(a) and ring_of.get(a) == ring_of.get(b)]
    rings_hit = sorted({ring_of[a] for a, _ in inside})
    return {"links": int(len(sig)), "links_within_planted_rings": len(inside),
            "rings_with_links": rings_hit}


def validate(data_dir: str | Path = "data", cfg: Config | None = None) -> dict:
    """Run the pipeline on the synthetic data and score it."""
    d = Path(data_dir)
    bids = ingest.load(d / "synthetic_tenders_ocds.json")
    registry = ingest.load_registry(d / "synthetic_registry.csv")
    truth = pd.read_csv(d / "synthetic_ground_truth_rings.csv", dtype=str)
    names = pd.read_csv(d / "synthetic_ground_truth_names.csv", dtype=str)
    ring_offices = pd.read_csv(d / "synthetic_ground_truth_offices.csv", dtype=str)
    res = run(bids, registry, cfg)
    return {"names": name_accuracy(res["name_map"], names),
            "pairs": pair_metrics(res["flagged"], true_pairs(truth)),
            "rings": ring_recovery(res["rings"], truth),
            "sweep": threshold_sweep(res["scored"], true_pairs(truth)),
            "offices": office_recovery(res["offices"], ring_offices),
            "recurrent": recurrent_check(res["relationships"], truth),
            "n_candidate_rings": res["summary"]["n_rings"]}


def main() -> None:
    """Command-line entry point."""
    ap = argparse.ArgumentParser(description="Validate on synthetic ground truth.")
    ap.add_argument("--data", default="data")
    ap.add_argument("--config")
    ap.add_argument("--json", help="write results to this JSON file")
    a = ap.parse_args()
    cfg = Config.from_json(a.config) if a.config else Config()
    r = validate(a.data, cfg)
    n, p = r["names"], r["pairs"]
    print("SYNTHETIC DATA VALIDATION (planted rings only; not evidence about real data)")
    print(f"Name resolution: {n['correct']}/{n['names']} correct "
          f"({n['accuracy']:.2%}), {n['wrong_firm']} wrong firm, {n['unresolved']} unresolved")
    print(f"Pairs: flagged {p['flagged']}, true {p['true_pairs']}, TP {p['true_positives']}, "
          f"FP {p['false_positives']}")
    print(f"Precision {p['precision']:.3f}  Recall {p['recall']:.3f}  F1 {p['f1']:.3f}")
    print(f"Candidate rings: {r['n_candidate_rings']}")
    for x in r["rings"]:
        print(f"  {x['planted_ring']} (size {x['size']}): best match {x['best_candidate']}, "
              f"Jaccard {x['jaccard']:.2f}")
    o, rc = r["offices"], r["recurrent"]
    print(f"Offices: {o['in_top_k']} of {o['planted_offices']} planted ring offices "
          f"in the top {o['planted_offices']} of the ranking")
    print(f"Recurrent loser->winner links: {rc['links']} "
          f"({rc['links_within_planted_rings']} within planted rings; rings: "
          f"{', '.join(rc['rings_with_links']) or 'none'})")
    print("Threshold sweep (pairs):")
    for x in r["sweep"]:
        print(f"  >= {x['threshold']:.2f}: flagged {x['flagged']:3d}  "
              f"precision {x['precision']:.3f}  recall {x['recall']:.3f}")
    if a.json:
        Path(a.json).write_text(json.dumps(r, indent=2))


if __name__ == "__main__":
    main()
