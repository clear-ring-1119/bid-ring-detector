"""Rank procuring offices by exposure to flagged pairs.

A tender is "flagged" if at least one flagged pair bid on it together.
Offices are ranked by the share of their tenders that are flagged, with
the value of those tenders shown alongside. A high share points to where
a reviewer should look first; it says nothing about staff conduct.
"""

from __future__ import annotations

import pandas as pd


def flagged_tenders(bids: pd.DataFrame, flagged_pairs: pd.DataFrame) -> set[str]:
    """Return the set of tenders where a flagged pair bid together."""
    if flagged_pairs.empty:
        return set()
    by_tender = bids.groupby("ocid")["firm_id"].apply(set)
    pairs = list(zip(flagged_pairs["firm_a"], flagged_pairs["firm_b"]))
    return {o for o, firms in by_tender.items()
            if any(a in firms and b in firms for a, b in pairs)}


def office_risk(bids: pd.DataFrame, flagged_pairs: pd.DataFrame,
                min_tenders: int = 10, relationships: pd.DataFrame | None = None,
                kcore: dict | None = None) -> pd.DataFrame:
    """One row per office with flagged share, value at risk and context.

    If ``relationships`` (significant loser -> winner pairs) is given, also
    adds ``tender_exposure``: the share of the office's contested tenders
    (two or more bidders) where such a pair bid together, after Villamil and
    Kertész. If ``kcore`` is given, adds the highest k-core of any firm in a
    relationship active at the office.

    Offices with fewer than ``min_tenders`` tenders are kept but marked
    ``low_volume`` because their shares are unstable.
    """
    flagged = flagged_tenders(bids, flagged_pairs)
    exposed: set[str] = set()
    if relationships is not None and not relationships.empty:
        sig = relationships[relationships["significant"]].rename(
            columns={"loser": "firm_a", "winner": "firm_b"})
        exposed = flagged_tenders(bids, sig)
    t = (bids.groupby("ocid")
             .agg(office_id=("office_id", "first"), office_name=("office_name", "first"),
                  region=("region", "first"), value=("estimated_value", "first"),
                  n_bidders=("firm_id", "nunique"))
             .reset_index())
    t["flagged"] = t["ocid"].isin(flagged)
    t["single_bid"] = t["n_bidders"] == 1
    t["contested"] = t["n_bidders"] >= 2
    t["exposed"] = t["ocid"].isin(exposed) & t["contested"]
    t["flagged_value"] = t["value"].where(t["flagged"], 0.0)
    o = (t.groupby(["office_id", "office_name", "region"])
          .agg(n_tenders=("ocid", "count"), n_flagged=("flagged", "sum"),
               total_value=("value", "sum"), flagged_value=("flagged_value", "sum"),
               single_bid_share=("single_bid", "mean"),
               mean_bidders=("n_bidders", "mean"),
               n_contested=("contested", "sum"), n_exposed=("exposed", "sum"))
          .reset_index())
    o["tender_exposure"] = (o["n_exposed"] / o["n_contested"].where(o["n_contested"] > 0)).fillna(0.0)
    if kcore is not None:
        o["max_kcore"] = _office_kcore(bids, relationships, kcore, o["office_id"])
    o["flagged_share"] = o["n_flagged"] / o["n_tenders"]
    o["flagged_value_share"] = o["flagged_value"] / o["total_value"]
    o["low_volume"] = o["n_tenders"] < min_tenders
    for c in ("flagged_share", "flagged_value_share", "single_bid_share", "mean_bidders",
              "tender_exposure"):
        o[c] = o[c].round(3)
    o = o.sort_values(["flagged_share", "flagged_value"], ascending=False).reset_index(drop=True)
    o.insert(0, "rank", range(1, len(o) + 1))
    return o


def _office_kcore(bids, relationships, kcore, office_ids) -> list[int]:
    """Highest k-core among firms in significant relationships seen at each office."""
    if relationships is None or relationships.empty or not kcore:
        return [0] * len(office_ids)
    sig = relationships[relationships["significant"]]
    by_tender = bids.groupby("ocid").agg(office=("office_id", "first"),
                                         firms=("firm_id", lambda s: set(s)))
    best: dict[str, int] = {}
    pairs = list(zip(sig["loser"], sig["winner"]))
    for office, firms in zip(by_tender["office"], by_tender["firms"]):
        for a, b in pairs:
            if a in firms and b in firms:
                best[office] = max(best.get(office, 0), kcore.get(a, 0), kcore.get(b, 0))
    return [best.get(o, 0) for o in office_ids]
