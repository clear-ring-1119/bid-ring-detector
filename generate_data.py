"""Generate SYNTHETIC procurement data for testing the detector.

Everything this script writes is invented. Firm names, people, addresses,
offices and amounts are random. Nothing here describes a real firm, person
or contract.

Outputs (in ``data/`` by default):

* ``synthetic_tenders_ocds.json``   OCDS-style releases (tender, bids, award)
* ``synthetic_bids.csv``            the same bids, flattened
* ``synthetic_registry.csv``        a synthetic corporate registry
* ``synthetic_ground_truth_rings.csv``  which firms belong to planted rings
* ``synthetic_ground_truth_names.csv``  true firm behind each typed bidder name
* ``synthetic_ground_truth_offices.csv``  offices where each ring operates

Planted behaviour (the "ground truth"):

* Ring members bid together on the ring's tenders.
* Winners rotate (or, in one ring, a single winner uses pure cover bidders).
* Losing members bid 3-10% above the designated winner.
* Some rings share directors or addresses in the registry.
* Some rings submit bids within minutes of each other.

Usage::

    python generate_data.py --seed 42 --out data
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

REGIONS = ["NCR", "CAR", "Region III", "Region IV-A", "Region V",
           "Region VI", "Region VII", "Region XI"]
CITIES = {
    "NCR": ["Quezon City", "Pasig", "Makati", "Caloocan", "Taguig"],
    "CAR": ["Baguio", "La Trinidad", "Tabuk", "Bontoc", "Bangued"],
    "Region III": ["San Fernando", "Angeles", "Malolos", "Tarlac", "Cabanatuan"],
    "Region IV-A": ["Calamba", "Batangas", "Lucena", "Antipolo", "Imus"],
    "Region V": ["Legazpi", "Naga", "Sorsogon", "Iriga", "Daet"],
    "Region VI": ["Iloilo", "Roxas", "Kalibo", "San Jose", "Bacolod"],
    "Region VII": ["Cebu", "Mandaue", "Tagbilaran", "Dumaguete", "Lapu-Lapu"],
    "Region XI": ["Davao", "Tagum", "Digos", "Mati", "Panabo"],
}
SURNAMES = ["Santos", "Reyes", "Cruz", "Bautista", "Ocampo", "Garcia", "Mendoza",
            "Torres", "Villanueva", "Ramos", "Aquino", "Navarro", "Castillo",
            "Flores", "Gonzales", "Dela Cruz", "Tan", "Lim", "Uy", "Sy", "Chua",
            "Domingo", "Pascual", "Salazar", "Manalo", "Lacson", "Soriano",
            "Valdez", "Mercado", "Aguilar", "Rivera", "Fernandez", "Morales"]
FIRSTNAMES = ["Jose", "Maria", "Juan", "Ana", "Ramon", "Lourdes", "Eduardo",
              "Rosario", "Antonio", "Carmela", "Ricardo", "Teresita", "Rogelio",
              "Marites", "Danilo", "Imelda", "Fernando", "Cristina", "Romeo",
              "Gloria", "Ernesto", "Liza", "Arnel", "Josefina", "Wilfredo"]
STEMS = ["Mabuhay", "Bayanihan", "Tagumpay", "Pag-asa", "Bagong Lahi", "Silangan",
         "Kalayaan", "Liwanag", "Masagana", "Kabisig", "Pinoy", "Bituin",
         "Golden", "Pacific", "Archipelago", "Island", "Sunrise", "Northstar",
         "Summit", "Metro", "Prime", "United", "Triple", "Apex", "Evergreen"]
TRADES = ["Construction", "Builders", "Engineering", "Development",
          "Construction & Supply", "Builders & Trading", "Infra Works",
          "Contractors", "Engineering Services", "Civil Works"]
FORMS = ["Corp.", "Inc.", "Co.", "Enterprises"]
STREETS = ["Rizal St.", "Mabini Ave.", "Bonifacio St.", "Quezon Blvd.",
           "Luna St.", "Burgos St.", "National Highway", "Del Pilar St.",
           "Osmeña Blvd.", "Magsaysay Ave."]
CATEGORIES = ["road", "bridge", "flood control", "school building",
              "drainage", "multi-purpose building"]

START = datetime(2022, 1, 1)
END = datetime(2025, 12, 31)


@dataclass
class RingSpec:
    """A planted ring and the behaviours it shows."""

    ring_id: str
    size: int
    n_tenders: int
    mode: str  # "rotate" or "cover" (one winner, pure covers)
    shared_director: bool
    shared_address: bool
    tight_timing: bool
    firm_ids: list = field(default_factory=list)
    office_ids: list = field(default_factory=list)


RINGS = [
    RingSpec("R1", 4, 70, "rotate", True, False, True),
    RingSpec("R2", 3, 50, "cover", False, True, True),
    RingSpec("R3", 5, 60, "rotate", False, False, True),
    RingSpec("R4", 3, 40, "rotate", True, True, False),
]


def person(rng: random.Random) -> str:
    """A random Filipino-style personal name (synthetic)."""
    return f"{rng.choice(FIRSTNAMES)} {rng.choice('ABCDEFGHJLMPRST')}. {rng.choice(SURNAMES)}"


def address(rng: random.Random, region: str) -> str:
    """A random street address in a region (synthetic)."""
    return f"{rng.randint(1, 999)} {rng.choice(STREETS)}, {rng.choice(CITIES[region])}"


def make_firms(rng: random.Random, n: int) -> list[dict]:
    """Create ``n`` firms with unique names, home regions and directors."""
    firms, seen = [], set()
    while len(firms) < n:
        stem = rng.choice(STEMS + SURNAMES)
        if rng.random() < 0.25:
            stem = "".join(rng.choice("ABCDEGJKLMRST") for _ in range(3))
        name = f"{stem} {rng.choice(TRADES)} {rng.choice(FORMS)}"
        if name in seen:
            continue
        seen.add(name)
        region = rng.choice(REGIONS)
        firms.append({
            "firm_id": f"F{len(firms) + 1:04d}",
            "registered_name": name,
            "region": region,
            "address": address(rng, region),
            "directors": [person(rng) for _ in range(rng.randint(1, 3))],
            "activity": rng.paretovariate(1.5),  # skewed: a few big, busy firms
            "markup": 0.0,
        })
    return firms


def make_offices(rng: random.Random, n: int) -> list[dict]:
    """Create ``n`` procuring offices spread over the regions."""
    offices = []
    for i in range(n):
        region = REGIONS[i % len(REGIONS)]
        city = CITIES[region][(i // len(REGIONS)) % len(CITIES[region])]
        offices.append({"office_id": f"O{i + 1:03d}",
                        "name": f"{city} District Engineering Office",
                        "region": region})
    return offices


def name_variant(rng: random.Random, name: str) -> str:
    """Return how a clerk might type the name: case, punctuation, spelling."""
    v = name
    r = rng.random()
    if r < 0.15:
        v = v.upper()
    elif r < 0.25:
        v = v.replace(".", "")
    elif r < 0.32:
        v = v.replace("Corp.", "Corporation").replace("Inc.", "Incorporated")
    elif r < 0.36:
        v = v.replace("&", "and")
    elif r < 0.39 and len(v) > 8:  # adjacent-letter typo
        i = rng.randint(1, len(v) - 3)
        v = v[:i] + v[i + 1] + v[i] + v[i + 2:]
    return v


def random_date(rng: random.Random) -> datetime:
    """A random closing date between 2022 and 2025, set at 10:00."""
    days = rng.randint(0, (END - START).days)
    return (START + timedelta(days=days)).replace(hour=10)


def honest_submit_time(rng: random.Random, close: datetime) -> datetime:
    """Honest bidders cluster towards the deadline but not in lockstep."""
    minutes = min(rng.expovariate(1 / 300), 72 * 60)
    return close - timedelta(minutes=minutes)


def generate(seed: int = 42, n_tenders: int = 5000, n_firms: int = 400,
             n_offices: int = 40) -> dict:
    """Build the full synthetic dataset and return it as Python objects."""
    rng = random.Random(seed)
    firms = make_firms(rng, n_firms)
    offices = make_offices(rng, n_offices)
    by_region = {r: [f for f in firms if f["region"] == r] for r in REGIONS}

    # Each office has a pool of firms that usually bid there.
    office_pool = {}
    for o in offices:
        local = by_region[o["region"]]
        pool = rng.sample(local, min(len(local), rng.randint(12, 18)))
        pool += rng.sample(firms, 3)  # a few out-of-region bidders
        office_pool[o["office_id"]] = pool

    # Plant rings: members from one region, active at 2-3 offices there.
    used = set()
    ring_regions = ["Region VII", "Region V", "Region III", "Region XI"]
    for spec, region in zip(RINGS, ring_regions):
        cands = [f for f in by_region[region] if f["firm_id"] not in used]
        members = rng.sample(cands, spec.size)
        spec.firm_ids = [m["firm_id"] for m in members]
        used.update(spec.firm_ids)
        offs = [o for o in offices if o["region"] == region]
        spec.office_ids = [o["office_id"] for o in rng.sample(offs, min(3, len(offs)))]
        if spec.shared_director:
            d = person(rng)
            for m in members:
                m["directors"] = [d] + m["directors"][:1]
        if spec.shared_address:
            a = address(rng, region)
            for m in members[: max(2, spec.size - 1)]:
                m["address"] = a
        if spec.mode == "cover":  # covers bid high everywhere: they rarely win
            for m in members[1:]:
                m["markup"] = 0.12
                m["activity"] = 0.3
        for oid in spec.office_ids:  # members also bid normally at these offices
            pool = office_pool[oid]
            for m in members:
                if m not in pool:
                    pool.append(m)

    firm_by_id = {f["firm_id"]: f for f in firms}
    office_by_id = {o["office_id"]: o for o in offices}

    # Decide which tender slots belong to rings.
    ring_slots = []
    for spec in RINGS:
        ring_slots += [spec] * spec.n_tenders
    rng.shuffle(ring_slots)
    slot_ids = set(rng.sample(range(n_tenders), len(ring_slots)))
    slot_iter = iter(ring_slots)

    releases, flat_bids, name_truth = [], [], {}
    rotation_ptr = {s.ring_id: 0 for s in RINGS}
    for t in range(n_tenders):
        close = random_date(rng)
        est = round(rng.lognormvariate(16.5, 1.0), -3)  # PHP, ~15M median
        est = min(max(est, 1_000_000), 400_000_000)
        bids = []  # (firm_id, amount, submitted_at)
        if t in slot_ids:
            spec = next(slot_iter)
            office = office_by_id[rng.choice(spec.office_ids)]
            members = list(spec.firm_ids)
            if spec.mode == "rotate":
                winner = members[rotation_ptr[spec.ring_id] % len(members)]
                rotation_ptr[spec.ring_id] += 1
                if rng.random() < 0.15 and len(members) > 3:
                    members.remove(rng.choice([m for m in members if m != winner]))
            else:
                winner = members[0]
            win_amt = est * rng.uniform(0.96, 0.995)
            base_time = close - timedelta(minutes=rng.uniform(20, 600))
            for m in members:
                amt = win_amt if m == winner else win_amt * rng.uniform(1.03, 1.10)
                if spec.tight_timing:
                    ts = base_time + timedelta(minutes=rng.uniform(0, 8))
                else:
                    ts = honest_submit_time(rng, close)
                bids.append((m, amt, ts))
            for o in rng.sample(office_pool[office["office_id"]], rng.randint(0, 1)):
                if o["firm_id"] not in members:  # an outsider who prices high
                    bids.append((o["firm_id"], est * rng.uniform(1.0, 1.08),
                                 honest_submit_time(rng, close)))
        else:
            office = rng.choice(offices)
            pool = office_pool[office["office_id"]]
            k = min(len(pool), rng.choice([1, 2, 3, 3, 4, 4, 5, 5, 6, 7]))
            weights = [f["activity"] for f in pool]
            chosen = set()
            while len(chosen) < k:
                chosen.add(rng.choices(pool, weights=weights)[0]["firm_id"])
            for fid in sorted(chosen):  # sorted: set order varies between runs
                f = firm_by_id[fid]
                amt = est * rng.uniform(0.85, 1.02) * (1 + f["markup"])
                bids.append((fid, amt, honest_submit_time(rng, close)))
            winner = None
        bids.sort(key=lambda b: b[1])
        if winner is None:  # lowest responsive bid wins; occasionally disqualified
            winner = bids[0][0]
            if len(bids) > 1 and rng.random() < 0.05:
                winner = bids[1][0]

        ocid = f"ocds-synthetic-{t + 1:05d}"
        details, award_supplier = [], None
        for fid, amt, ts in bids:
            f = firm_by_id[fid]
            shown = name_variant(rng, f["registered_name"])
            name_truth[shown] = fid
            details.append({
                "id": f"{ocid}-bid-{len(details) + 1}",
                "date": ts.isoformat(timespec="minutes"),
                "status": "valid",
                "tenderers": [{"name": shown}],
                "value": {"amount": round(amt, 2), "currency": "PHP"},
            })
            flat_bids.append({
                "ocid": ocid, "office_id": office["office_id"],
                "office_name": office["name"], "region": office["region"],
                "tender_close": close.isoformat(timespec="minutes"),
                "estimated_value": est, "bidder_name": shown,
                "bid_amount": round(amt, 2),
                "submitted_at": ts.isoformat(timespec="minutes"),
                "is_winner": int(fid == winner),
            })
            if fid == winner:
                award_supplier = shown
        releases.append({
            "ocid": ocid,
            "date": close.isoformat(timespec="minutes"),
            "buyer": {"id": office["office_id"], "name": office["name"],
                      "region": office["region"]},
            "tender": {"id": ocid, "title": f"Synthetic {rng.choice(CATEGORIES)} project",
                       "value": {"amount": est, "currency": "PHP"},
                       "tenderPeriod": {"endDate": close.isoformat(timespec="minutes")}},
            "bids": {"details": details},
            "awards": [{"id": f"{ocid}-award", "status": "active",
                        "suppliers": [{"name": award_supplier}]}],
        })

    registry = [{"firm_id": f["firm_id"], "registered_name": f["registered_name"],
                 "region": f["region"], "address": f["address"],
                 "directors": "; ".join(f["directors"])} for f in firms]
    truth = [{"ring_id": s.ring_id, "firm_id": fid, "mode": s.mode}
             for s in RINGS for fid in s.firm_ids]
    ring_offices = [{"ring_id": s.ring_id, "office_id": oid}
                    for s in RINGS for oid in s.office_ids]
    names = [{"bidder_name": k, "firm_id": v} for k, v in sorted(name_truth.items())]
    return {"releases": releases, "bids": flat_bids, "registry": registry,
            "truth": truth, "name_truth": names, "ring_offices": ring_offices}


def write_csv(path: Path, rows: list[dict]) -> None:
    """Write a list of dicts as CSV."""
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    """Command-line entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--tenders", type=int, default=5000)
    ap.add_argument("--firms", type=int, default=400)
    ap.add_argument("--offices", type=int, default=40)
    ap.add_argument("--out", default="data")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    d = generate(a.seed, a.tenders, a.firms, a.offices)
    pkg = {"_note": "SYNTHETIC DATA. Invented for testing. Not real contracts.",
           "releases": d["releases"]}
    (out / "synthetic_tenders_ocds.json").write_text(json.dumps(pkg), encoding="utf-8")
    write_csv(out / "synthetic_bids.csv", d["bids"])
    write_csv(out / "synthetic_registry.csv", d["registry"])
    write_csv(out / "synthetic_ground_truth_rings.csv", d["truth"])
    write_csv(out / "synthetic_ground_truth_names.csv", d["name_truth"])
    write_csv(out / "synthetic_ground_truth_offices.csv", d["ring_offices"])
    print(f"Wrote {len(d['releases'])} synthetic tenders, {len(d['bids'])} bids, "
          f"{len(d['registry'])} firms to {out}/")


if __name__ == "__main__":
    main()
