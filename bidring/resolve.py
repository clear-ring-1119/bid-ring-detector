"""Firm resolution: map the names typed on bids to registry firm IDs.

Step 1 normalises names (case, punctuation, spellings of legal forms).
Step 2 matches exact normalised names, then falls back to a fuzzy match
(difflib ratio on letters-only names) within names sharing the same first
three characters. Names that
cannot be matched get a stable ``UNRESOLVED:<name>`` ID so they still
count as one bidder.

This is deliberately simple. Real data needs registry numbers (SEC,
PhilGEPS, TIN) where available, and a human check of borderline matches.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

import pandas as pd

# Spelling variants of legal forms mapped to one canonical token. They are
# kept, not dropped: "X Builders Inc." and "X Builders Co." can be two
# different firms (often sister firms, which matters here).
LEGAL_FORMS = {
    "corporation": "corp", "incorporated": "inc", "company": "co",
    "limited": "ltd", "enterprise": "enterprises",
}


def normalise(name: str) -> str:
    """Upper-case, swap '&' for 'AND', drop punctuation, standardise legal forms."""
    s = str(name).lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    tokens = [LEGAL_FORMS.get(t, t) for t in s.split()]
    return " ".join(tokens).upper()


def compact(name: str) -> str:
    """The normalised name with spaces removed, lower case. Used for fuzzy matching,
    so that a slipped space or swapped letters still score close."""
    return normalise(name).replace(" ", "").lower()


def _block(key: str) -> str:
    """Blocking key for fuzzy candidates: first three characters."""
    return key[:3]


def build_index(registry: pd.DataFrame) -> tuple[dict, dict]:
    """Return (exact lookup on normalised names, fuzzy blocks on compact names)."""
    exact, blocks = {}, {}
    for fid, name in zip(registry["firm_id"], registry["registered_name"]):
        exact.setdefault(normalise(name), fid)
        c = compact(name)
        blocks.setdefault(_block(c), []).append((c, fid))
    return exact, blocks


def match_name(name: str, exact: dict, blocks: dict,
               threshold: float = 0.90) -> tuple[str, float]:
    """Return (firm_id, score) for one name; score 1.0 means exact."""
    n = normalise(name)
    if n in exact:
        return exact[n], 1.0
    c = compact(name)
    candidates = blocks.get(_block(c)) or [x for b in blocks.values() for x in b]
    best_id, best = None, 0.0
    for cand, fid in candidates:
        sm = SequenceMatcher(None, c, cand)
        if sm.quick_ratio() < threshold:
            continue
        r = sm.ratio()
        if r > best:
            best_id, best = fid, r
    if best_id is not None and best >= threshold:
        return best_id, best
    return f"UNRESOLVED:{n}", 0.0


def resolve_bids(bids: pd.DataFrame, registry: pd.DataFrame,
                 threshold: float = 0.90) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Add a ``firm_id`` column to bids.

    Returns (bids with firm_id, name map with match scores for review).
    """
    exact, blocks = build_index(registry)
    names = bids["bidder_name"].astype(str).unique()
    rows = []
    for nm in names:
        fid, score = match_name(nm, exact, blocks, threshold)
        rows.append({"bidder_name": nm, "firm_id": fid, "match_score": round(score, 3)})
    name_map = pd.DataFrame(rows)
    out = bids.merge(name_map[["bidder_name", "firm_id"]], on="bidder_name", how="left")
    # One firm should appear once per tender even if typed twice.
    out["is_winner"] = out.groupby(["ocid", "firm_id"])["is_winner"].transform("max")
    out = (out.sort_values(["ocid", "firm_id", "bid_amount"])
              .drop_duplicates(["ocid", "firm_id"], keep="first")
              .reset_index(drop=True))
    return out, name_map
