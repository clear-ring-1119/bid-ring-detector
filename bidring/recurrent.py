"""Directed "recurrent loser -> recurrent winner" relationships.

A simplified take on the idea in Villamil and Kertész (2026): for each
ordered pair (loser L, winner W) that bid together at least
``min_cobids`` times, test whether W wins more often when L also bids
than W's win rate on its other contested tenders would predict
(one-sided binomial test, with a smoothed baseline). P-values are corrected for the number of
tests with Benjamini-Hochberg. Significant pairs form a directed graph
with links from losers to winners.

The paper's own test, market definition and k-core classification are
more careful than this; see the README.
"""

from __future__ import annotations

from math import comb

import networkx as nx
import pandas as pd


def binom_sf(k: int, n: int, p: float) -> float:
    """P(X >= k) for X ~ Binomial(n, p)."""
    if k <= 0:
        return 1.0
    p = min(max(p, 1e-9), 1 - 1e-9)
    return min(1.0, sum(comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1)))


def bh_adjust(pvals: list[float]) -> list[float]:
    """Benjamini-Hochberg adjusted p-values, same order as input."""
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    adj = [0.0] * m
    prev = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        prev = min(prev, pvals[i] * m / rank)
        adj[i] = prev
    return adj


def recurrent_relationships(bids: pd.DataFrame, graph: nx.Graph,
                            min_cobids: int = 8, alpha: float = 0.01) -> pd.DataFrame:
    """Test every ordered pair on the co-bidding graph; return all tests.

    Columns: loser, winner, n_cobids, wins_together, rate_together,
    rate_elsewhere, p_value, q_value, significant.
    """
    contested = bids.groupby("ocid")["firm_id"].transform("nunique") >= 2
    b = bids[contested]
    winner = b[b["is_winner"] == 1].set_index("ocid")["firm_id"].to_dict()
    tenders_of = b.groupby("firm_id")["ocid"].apply(set).to_dict()

    rows = []
    for x, y, d in graph.edges(data=True):
        if d["n"] < min_cobids:
            continue
        shared = set(d["ocids"])
        for loser, win in ((x, y), (y, x)):
            n = len(shared)
            k = sum(winner.get(o) == win for o in shared)
            other = tenders_of.get(win, set()) - shared
            # Laplace smoothing: a firm with no wins elsewhere is not given a
            # baseline of exactly zero, which would make any win "significant".
            base = (sum(winner.get(o) == win for o in other) + 1) / (len(other) + 2)
            rows.append({"loser": loser, "winner": win, "n_cobids": n,
                         "wins_together": k, "rate_together": round(k / n, 3),
                         "rate_elsewhere": round(base, 3),
                         "p_value": binom_sf(k, n, base)})
    cols = ["loser", "winner", "n_cobids", "wins_together", "rate_together",
            "rate_elsewhere", "p_value", "q_value", "significant"]
    if not rows:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(rows)
    df["q_value"] = bh_adjust(df["p_value"].tolist())
    df["significant"] = df["q_value"] < alpha
    return df.sort_values("q_value").reset_index(drop=True)[cols]


def directed_graph(rel: pd.DataFrame) -> nx.DiGraph:
    """Directed graph of significant relationships (loser -> winner)."""
    g = nx.DiGraph()
    for r in rel[rel["significant"]].itertuples():
        g.add_edge(r.loser, r.winner, n=r.n_cobids, q=r.q_value)
    return g


def max_kcore(g: nx.DiGraph) -> dict[str, int]:
    """Core number of each firm in the undirected version of the graph.

    A higher maximum k-core means a more interconnected group of firms.
    """
    if g.number_of_nodes() == 0:
        return {}
    u = nx.Graph(g.to_undirected())
    u.remove_edges_from(nx.selfloop_edges(u))
    return nx.core_number(u)
