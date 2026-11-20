"""Write outputs: summary CSVs, one evidence pack per flagged pair, and an HTML report."""

from __future__ import annotations

import html
import json
from pathlib import Path

import pandas as pd

EVIDENCE_COLS = ["ocid", "office_id", "office_name", "tender_close", "estimated_value",
                 "firm_id", "bidder_name", "bid_amount", "pct_of_winning_bid",
                 "submitted_at", "is_winner"]


def evidence_pack(bids: pd.DataFrame, pair_row: pd.Series) -> pd.DataFrame:
    """All bids on the tenders where the pair bid together, one row per bid.

    Includes every bidder on those tenders (not just the pair), so a reader
    can see who else took part and who won.
    """
    a, b = pair_row["firm_a"], pair_row["firm_b"]
    per = bids.groupby("ocid")["firm_id"].apply(set)
    ocids = [o for o, f in per.items() if a in f and b in f]
    ev = bids[bids["ocid"].isin(ocids)].copy()
    win_amt = ev[ev["is_winner"] == 1].set_index("ocid")["bid_amount"]
    ev["pct_of_winning_bid"] = (ev["bid_amount"] / ev["ocid"].map(win_amt) * 100).round(1)
    ev = ev.sort_values(["tender_close", "ocid", "bid_amount"])
    return ev[EVIDENCE_COLS].reset_index(drop=True)


def write_outputs(out_dir: str | Path, result: dict, firm_names: dict[str, str]) -> Path:
    """Write all outputs to ``out_dir`` and return the HTML report path."""
    out = Path(out_dir)
    (out / "evidence").mkdir(parents=True, exist_ok=True)
    flagged, rings, offices = result["flagged"], result["rings"], result["offices"]

    result["scored"].to_csv(out / "all_scored_pairs.csv", index=False)
    flagged.to_csv(out / "flagged_pairs.csv", index=False)
    rings.assign(firm_name=rings["firm_id"].map(firm_names)).to_csv(
        out / "candidate_rings.csv", index=False)
    offices.to_csv(out / "office_risk.csv", index=False)
    result["name_map"].to_csv(out / "name_resolution.csv", index=False)
    rel = result.get("relationships")
    if rel is not None:
        rel[rel["significant"]].to_csv(out / "recurrent_relationships.csv", index=False)
    (out / "config_used.json").write_text(json.dumps(result["config"], indent=2))

    for _, row in flagged.iterrows():
        evidence_pack(result["bids"], row).to_csv(
            out / "evidence" / f"{row.firm_a}__{row.firm_b}.csv", index=False)

    path = out / "report.html"
    path.write_text(render_html(result, firm_names), encoding="utf-8")
    return path


def _table(df: pd.DataFrame, max_rows: int = 50) -> str:
    """Render a DataFrame as an escaped HTML table."""
    if df.empty:
        return "<p>None.</p>"
    return df.head(max_rows).to_html(index=False, escape=True, border=0, classes="t")


def render_html(result: dict, firm_names: dict[str, str]) -> str:
    """Build a single self-contained HTML page."""
    flagged = result["flagged"].copy()
    flagged.insert(1, "name_a", flagged["firm_a"].map(firm_names))
    flagged.insert(3, "name_b", flagged["firm_b"].map(firm_names))
    show = flagged[["firm_a", "name_a", "firm_b", "name_b", "n_cobids", "overlap",
                    "behaviour", "timing", "registry", "cover_bidder", "score"]]
    rings = result["rings"].assign(firm_name=result["rings"]["firm_id"].map(firm_names))
    ring_summary = (rings.groupby("ring_id")
                    .agg(size=("firm_id", "count"), max_score=("ring_max_score", "first"),
                         firms=("firm_name", lambda s: "; ".join(s)))
                    .reset_index()) if not rings.empty else rings
    ocols = ["rank", "office_id", "office_name", "region", "n_tenders", "n_flagged",
             "flagged_share", "flagged_value_share", "tender_exposure", "max_kcore",
             "single_bid_share", "mean_bidders", "low_volume"]
    offices = result["offices"][[c for c in ocols if c in result["offices"].columns]]
    rel = result.get("relationships")
    sig = rel[rel["significant"]].copy() if rel is not None and not rel.empty else pd.DataFrame()
    if not sig.empty:
        sig.insert(1, "loser_name", sig["loser"].map(firm_names))
        sig.insert(3, "winner_name", sig["winner"].map(firm_names))
        sig["q_value"] = sig["q_value"].map(lambda q: f"{q:.1e}")
        sig = sig.drop(columns=["p_value", "significant"])
    s = result["summary"]
    note = html.escape(result.get("data_note", ""))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Bid-ring screening report</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:1100px;margin:2em auto;padding:0 1em;color:#222}}
h1{{font-size:1.5em}} h2{{font-size:1.15em;margin-top:2em}}
.warn{{background:#fff4d6;border:1px solid #e0c060;padding:.7em 1em}}
table.t{{border-collapse:collapse;font-size:.85em;width:100%}}
table.t th,table.t td{{border-bottom:1px solid #ddd;padding:4px 6px;text-align:left}}
table.t th{{background:#f3f3f3}}
</style></head><body>
<h1>Bid-ring screening report</h1>
<p class="warn">{note} Flags are screening signals for review, not findings of collusion.</p>
<p>Tenders: {s['n_tenders']:,} &middot; bids: {s['n_bids']:,} &middot; firms: {s['n_firms']:,}
&middot; pairs scored: {s['n_pairs_scored']:,} &middot; pairs flagged: {s['n_flagged']:,}
&middot; candidate rings: {s['n_rings']:,}
&middot; recurrent loser&rarr;winner links: {s.get('n_relationships', 0):,}</p>

<h2>Candidate rings</h2>
<p>Groups of firms linked by flagged pairs.</p>
{_table(ring_summary)}

<h2>Flagged pairs</h2>
<p>Each pair has an evidence pack in <code>evidence/&lt;firm_a&gt;__&lt;firm_b&gt;.csv</code>
listing every bid on the tenders they shared.</p>
{_table(show, 100)}

<h2>Recurrent loser &rarr; winner links</h2>
<p>Ordered pairs where the winner wins more often when the loser also bids
than on its other contested tenders (binomial test, Benjamini-Hochberg q &lt;
{result['config']['recurrent_alpha']}). Top 30 shown.</p>
{_table(sig, 30)}

<h2>Offices ranked by exposure</h2>
<p><b>flagged_share</b>: share of tenders where a flagged pair bid together.
<b>tender_exposure</b>: share of contested tenders involving a recurrent
loser&rarr;winner link. <b>max_kcore</b>: how interconnected the linked firms
are. Top 15 shown.</p>
{_table(offices, 15)}

<h2>How the score works</h2>
<ul>
<li><b>overlap</b>: shared tenders divided by the tenders of the less active firm.</li>
<li><b>behaviour</b>: share of shared tenders won by the pair's recurring core group.</li>
<li><b>timing</b>: share of shared tenders where both bids came in within
{result['config']['timing_window_minutes']} minutes.</li>
<li><b>registry</b>: 1.0 shared director, 0.75 shared address only.</li>
</ul>
<p>Flag threshold: {result['config']['flag_threshold']}. Settings are in <code>config_used.json</code>.</p>
</body></html>
"""
