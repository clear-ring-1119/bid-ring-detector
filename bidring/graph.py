"""Co-bidding graph: firms are nodes, an edge means they bid on the same tender.

Edge attribute ``n`` is the number of shared tenders and ``ocids`` lists
them. Candidate rings are the connected groups of flagged pairs.
"""

from __future__ import annotations

from collections import defaultdict
from itertools import combinations

import networkx as nx
import pandas as pd


def tender_bidders(bids: pd.DataFrame) -> dict[str, list[str]]:
    """Map each tender to the sorted list of firms that bid on it."""
    return {o: sorted(set(g)) for o, g in bids.groupby("ocid")["firm_id"]}


def build_cobid_graph(bids: pd.DataFrame, min_cobids: int = 1) -> nx.Graph:
    """Build the co-bidding graph, keeping edges with at least ``min_cobids`` shared tenders.

    Node attributes: ``n_bids`` and ``n_wins``.
    """
    pair_tenders: dict[tuple[str, str], list[str]] = defaultdict(list)
    for ocid, firms in tender_bidders(bids).items():
        for a, b in combinations(firms, 2):
            pair_tenders[(a, b)].append(ocid)

    g = nx.Graph()
    stats = bids.groupby("firm_id").agg(n_bids=("ocid", "nunique"),
                                        n_wins=("is_winner", "sum"))
    for fid, row in stats.iterrows():
        g.add_node(fid, n_bids=int(row.n_bids), n_wins=int(row.n_wins))
    for (a, b), ocids in pair_tenders.items():
        if len(ocids) >= min_cobids:
            g.add_edge(a, b, n=len(ocids), ocids=ocids)
    return g


def candidate_rings(flagged_pairs: pd.DataFrame) -> pd.DataFrame:
    """Group flagged pairs into connected components ("candidate rings").

    Returns one row per firm: ring_id, firm_id, ring_size, ring_max_score.
    Ring IDs are ordered by the strongest pair score in each group.
    """
    cols = ["ring_id", "firm_id", "ring_size", "ring_max_score"]
    if flagged_pairs.empty:
        return pd.DataFrame(columns=cols)
    g = nx.Graph()
    for r in flagged_pairs.itertuples():
        g.add_edge(r.firm_a, r.firm_b, score=r.score)
    comps = []
    for comp in nx.connected_components(g):
        sub = g.subgraph(comp)
        best = max(d["score"] for _, _, d in sub.edges(data=True))
        comps.append((best, sorted(comp)))
    comps.sort(key=lambda c: (-c[0], c[1]))
    rows = []
    for i, (best, members) in enumerate(comps, start=1):
        for fid in members:
            rows.append({"ring_id": f"C{i:02d}", "firm_id": fid,
                         "ring_size": len(members), "ring_max_score": round(best, 3)})
    return pd.DataFrame(rows, columns=cols)
