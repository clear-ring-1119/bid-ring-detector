"""Thresholds and weights, kept in one place so they can be tuned.

Load overrides from a JSON file with ``Config.from_json(path)``; any key
left out keeps its default.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path


@dataclass
class Config:
    """All tunable settings for the pipeline."""

    # Firm resolution
    fuzzy_threshold: float = 0.90      # difflib ratio needed to match a name

    # Co-bidding graph
    min_cobids: int = 8                # pairs bidding together fewer times are ignored

    # Pair signals
    overlap_prior: float = 8           # added to the smaller firm's bid count (shrinks small-sample overlap)
    core_share: float = 0.5            # firm counts as "core" if in >= this share of the pair's co-bids
    cover_max_win_rate: float = 0.05   # a firm winning less than this overall looks like a cover bidder
    timing_window_minutes: float = 10  # two bids this close in time count as "together"

    # Composite score weights (normalised to sum to 1)
    w_overlap: float = 0.30
    w_behaviour: float = 0.30
    w_timing: float = 0.20
    w_registry: float = 0.20

    # Recurrent-loser test
    recurrent_alpha: float = 0.01      # Benjamini-Hochberg q-value cut-off

    # Flagging
    flag_threshold: float = 0.50       # composite score needed to flag a pair

    @classmethod
    def from_json(cls, path: str | Path) -> "Config":
        """Read overrides from a JSON file; unknown keys raise an error."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"Unknown config keys: {sorted(unknown)}")
        return cls(**data)

    def weights(self) -> dict[str, float]:
        """Return the four weights normalised to sum to 1."""
        w = {"overlap": self.w_overlap, "behaviour": self.w_behaviour,
             "timing": self.w_timing, "registry": self.w_registry}
        total = sum(w.values())
        if total <= 0:
            raise ValueError("Weights must sum to more than zero")
        return {k: v / total for k, v in w.items()}

    def to_dict(self) -> dict:
        """Plain dict, for writing next to outputs."""
        return asdict(self)
