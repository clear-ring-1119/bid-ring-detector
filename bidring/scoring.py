"""Score each frequently co-bidding pair of firms.

Four signals, each between 0 and 1:

* ``overlap``    shared tenders / (tenders of the less active firm +
                 ``overlap_prior``). Ring members bid together far more than
                 chance. The prior stops a firm with a handful of bids, all
                 alongside one busy firm, from scoring a perfect 1.0.
* ``behaviour``  share of the pair's shared tenders won by a "core group"
                 (the pair plus any firm present in at least ``core_share``
                 of those tenders). In a ring, the winner comes from the same
                 small set and outsiders rarely win. Honest competitors lose
                 to a changing cast.
* ``timing``     share of shared tenders where the two bids were submitted
                 within ``timing_window_minutes`` of each other.
* ``registry``   1.0 for a shared director, 0.75 for a shared address only.

The composite score is a weighted sum. Two descriptive fields help
reading the evidence: ``cover_bidder`` (a firm in the pair that almost
never wins anywhere) and ``rotation`` (how many core firms took turns
winning, relative to core size).

These are screening signals, not proof. A shared address can be a
business centre; bidding together can be normal in a thin local market.
"""

from __future__ import annotations

from collections import Counter

import networkx as nx
import pandas as pd

from .config import Config


def _split(s: str) -> set[str]:
    """Split a '; '-separated director list into a set of cleaned names."""
    return {p.strip().upper() for p in str(s).split(";") if p.strip()}


def registry_links(registry: pd.DataFrame) -> tuple[dict, dict]:
    """Return (firm -> set of directors, firm -> normalised address)."""
    directors = {r.firm_id: _split(r.directors) for r in registry.itertuples()}
    addresses = {r.firm_id: " ".join(str(r.address).upper().split())
                 for r in registry.itertuples()}
    return directors, addresses


def score_pairs(bids: pd.DataFrame, graph: nx.Graph, registry: pd.DataFrame,
                cfg: Config) -> pd.DataFrame:
    """Score every edge in ``graph`` and return a table sorted by score."""
    w = cfg.weights()
    winner = bids[bids["is_winner"] == 1].set_index("ocid")["firm_id"].to_dict()
    bidders = bids.groupby("ocid")["firm_id"].apply(set).to_dict()
    times = bids.set_index(["ocid", "firm_id"])["submitted_at"].to_dict()
    directors, addresses = registry_links(registry)
    window = pd.Timedelta(minutes=cfg.timing_window_minutes)

    rows = []
    for a, b, d in graph.edges(data=True):
        if d["n"] < cfg.min_cobids:
            continue
        a, b = sorted((a, b))
        ocids = d["ocids"]
        n = len(ocids)
        na, nb = graph.nodes[a]["n_bids"], graph.nodes[b]["n_bids"]
        wa, wb = graph.nodes[a]["n_wins"], graph.nodes[b]["n_wins"]

        overlap = n / (min(na, nb) + cfg.overlap_prior)

        presence = Counter(f for o in ocids for f in bidders[o])
        core = {f for f, c in presence.items() if c / n >= cfg.core_share} | {a, b}
        core_wins = [winner.get(o) for o in ocids if winner.get(o) in core]
        behaviour = len(core_wins) / n
        rotation = len(set(core_wins)) / len(core)

        close = 0
        for o in ocids:
            ta, tb = times.get((o, a)), times.get((o, b))
            if pd.notna(ta) and pd.notna(tb) and abs(ta - tb) <= window:
                close += 1
        timing = close / n

        shared_dir = sorted(directors.get(a, set()) & directors.get(b, set()))
        same_addr = bool(addresses.get(a)) and addresses.get(a) == addresses.get(b)
        registry_sig = 1.0 if shared_dir else (0.75 if same_addr else 0.0)

        rate_a, rate_b = wa / na, wb / nb
        cover = [f for f, r in ((a, rate_a), (b, rate_b)) if r < cfg.cover_max_win_rate]

        score = (w["overlap"] * overlap + w["behaviour"] * behaviour
                 + w["timing"] * timing + w["registry"] * registry_sig)
        rows.append({
            "firm_a": a, "firm_b": b, "n_cobids": n,
            "bids_a": na, "bids_b": nb,
            "win_rate_a": round(rate_a, 3), "win_rate_b": round(rate_b, 3),
            "overlap": round(overlap, 3), "behaviour": round(behaviour, 3),
            "rotation": round(rotation, 3), "timing": round(timing, 3),
            "registry": registry_sig,
            "shared_directors": "; ".join(shared_dir),
            "shared_address": addresses.get(a) if same_addr else "",
            "cover_bidder": "; ".join(cover),
            "core_group": "; ".join(sorted(core)),
            "score": round(score, 4),
        })
    cols = ["firm_a", "firm_b", "n_cobids", "bids_a", "bids_b", "win_rate_a",
            "win_rate_b", "overlap", "behaviour", "rotation", "timing", "registry",
            "shared_directors", "shared_address", "cover_bidder", "core_group", "score"]
    out = pd.DataFrame(rows, columns=cols)
    return out.sort_values(["score", "n_cobids"], ascending=False).reset_index(drop=True)


def flag(scored: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Keep pairs at or above the flag threshold."""
    return scored[scored["score"] >= cfg.flag_threshold].reset_index(drop=True)
