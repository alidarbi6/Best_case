"""Synthetic raw data shaped like the WellView (``wvt_*``) tables.

Used by the tests and by ``best-case demo-data`` so that the whole pipeline can be run and
inspected without access to the production SQL Server.  The data deliberately contains the
situations the workflow has to cope with: text variants (``12 1/4"``), duplicate rows
(two rigs per job), an unfinished well, a drilled interval that straddles two formations,
formations without a bottom depth, wells outside the "new design" list, ...
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

# (database, [(well name, in new design?, completed?, days per section)])
_WORLD = {
    "SPH_Wells": [
        ("SPH-01", True, True, (4, 6, 3)),
        ("SPH-02", True, True, (3, 7, 4)),
        ("SPH-03", True, False, (5, 5, 0)),  # unfinished: last section still being drilled
        ("SPH-99", False, True, (2, 2, 2)),  # old design -> must be ignored
    ],
    "JR_Wells": [
        ("JR-03", True, True, (4, 5, 3)),
        ("JR-04", True, True, (3, 6, 3)),
        ("JR-11", False, True, (2, 2, 2)),
    ],
    "OtherDB": [],  # not selected by the database patterns
}
_SECTIONS = [  # (label as typed in WellView, from depth, to depth)
    ('17 1/2"', 0.0, 1300.0),
    (' 12 1/4" ', 1300.0, 2700.0),
    ("8 1/2", 2700.0, 3200.0),
]
_FORMATIONS = [  # (name as typed, top, bottom)
    ("Gachsaran Fm.", 0.0, 1500.0),
    ("FAHLIYAN", 1500.0, 2600.0),
    ("Ilam Fm", 2600.0, np.nan),  # bottom missing -> derived later
    ("TD", 3200.0, np.nan),
]
_DAY_PATTERN = [("4", 0.5), ("10", 0.25), ("11", 0.25)]  # (code1, fraction of the day)


class _Ids:
    def __init__(self):
        self.n = 0

    def __call__(self, prefix: str) -> str:
        self.n += 1
        return f"{prefix}{self.n:05d}"


def _database(name: str, wells: list, rng: np.random.Generator, ids: _Ids) -> dict[str, pd.DataFrame]:
    header, job, rig, report, timelog, wellbore = [], [], [], [], [], []
    ds, comp, param, form = [], [], [], []
    for w_idx, (wname, _new, completed, days) in enumerate(wells):
        idwell = ids("W")
        header.append({"idwell": idwell, "wellname": wname})
        start = dt.datetime(2024, 1, 1) + dt.timedelta(days=30 * (w_idx + 1))
        idjob = ids("J")
        job.append({"idwell": idwell, "idrec": idjob, "dttmend": start + dt.timedelta(days=60),
                    "dttmspud": start, "dttmstart": start,
                    "jobtyp": rng.choice(['Drilling - Original', '"drilling original"', "Drilling Original "])})
        for r in range(2 if w_idx == 0 else 1):  # two rigs on the first well -> duplicated job rows
            rig.append({"idwell": idwell, "idrecparent": idjob, "idrec": ids("R"), "contractor": "ACME",
                        "dttmend": start + dt.timedelta(days=60), "dttmstart": start, "rigno": f"R{r + 1}"})
        bore = ids("B")
        wellbore.append({"idwell": idwell, "idrec": bore, "des": "Original Hole"})
        sidetrack = ids("B")
        wellbore.append({"idwell": idwell, "idrec": sidetrack, "des": "Sidetrack 1"})

        for f_name, top, btm in _FORMATIONS:
            form.append({"idwell": idwell, "idrecparent": bore, "idrec": ids("F"), "depthdrillingbtm": btm,
                         "depthdrillingtop": top, "depthfinalsource": "log", "formname": f_name, "layername": None})

        day = start
        sysseq_global = 0
        # day 0: rig move
        rep = _report(report, idwell, idjob, ids, day)
        timelog.append(_tl(idwell, rep, "40", "P", "MOVE", 1.0, bore, 1, 6, "Rig move", ids))
        day += dt.timedelta(days=1)
        for s_idx, n_days in enumerate(days):
            if n_days == 0:
                continue
            label, d0, d1 = _SECTIONS[s_idx]
            string = ids("S")
            ds.append({"idwell": idwell, "idrecparent": idjob, "idrec": string, "bitno": f"BIT{s_idx + 1}",
                       "bittfa": 1.2, "com": "bit run", "des": f"BHA {s_idx + 1}", "stringno": s_idx + 1,
                       "wearbearing": None, "weardull": "1", "weargauge": "I", "wearinner": 1, "wearloc": "S",
                       "wearother": None, "wearouter": 2, "wearpulled": "BT"})
            for k in range(3):
                comp.append({"idwell": idwell, "idrecparent": string, "idrec": ids("C"), "com": f"comp {k}",
                             "des": ["Bit", "Motor", "Collar"][k], "grade": "G105", "hoursstart": 10.5 * k,
                             "joints": k + 1, "length": 3.5 * (k + 1), "make": "MK", "model": f"M{k}", "sysseq": k + 1})
            depths = np.linspace(d0, d1, n_days * 2 + 1)
            for d in range(n_days):
                rep = _report(report, idwell, idjob, ids, day)
                for seq, (c1, frac) in enumerate(_DAY_PATTERN, start=1):
                    com = "increase WOB to 20" if (d == 0 and seq == 1) else "routine"
                    timelog.append(_tl(idwell, rep, c1, "P", label, frac * float(rng.choice([1.0, 1.0, 1.0])), bore, seq,
                                       2 + (seq % 5), com, ids))
                timelog.append(_tl(idwell, rep, "26", "U", label, 0.0, bore, 4, 2, "waiting", ids))  # NPT-like, zero length
                for half in range(2):
                    i = d * 2 + half
                    t0 = day + dt.timedelta(hours=12 * half)
                    # shift the very first interval so that it straddles formations when possible
                    ds_ = depths[i] - (50 if half == 0 and d == 1 and s_idx == 1 else 0)
                    param.append({"idwell": idwell, "idrecparent": string, "idrec": ids("P"), "depthend": depths[i + 1],
                                  "depthstart": ds_, "dttmend": t0 + dt.timedelta(hours=11, minutes=59),
                                  "dttmstart": t0, "hookloadoffbottom": 100.0, "hookloadpickup": 110.0,
                                  "hookloadrotating": 105.0, "hookloadslackoff": 95.0, "idrecwellbore": bore,
                                  "liquidinjrate": 30.0, "rpmmotor": 60.0, "rpmstring": 80.0, "sppdiff": 5.0,
                                  "sppdrill": 200.0, "tfo": 0.0, "tmcirc": 1.0, "tmdrill": 5.0, "torquedrill": 8.0,
                                  "torqueoffbtm": 6.0, "wob": 20.0 + i})
                day += dt.timedelta(days=1)
        if completed:
            rep = _report(report, idwell, idjob, ids, day)
            timelog.append(_tl(idwell, rep, "39", "P", "Completion", 1.0, bore, 1, 5, "run completion", ids))
    return {
        "well_header": pd.DataFrame(header),
        "job": pd.DataFrame(job),
        "rig": pd.DataFrame(rig),
        "report": pd.DataFrame(report),
        "timelog": pd.DataFrame(timelog),
        "wellbore": pd.DataFrame(wellbore),
        "drillstring": pd.DataFrame(ds),
        "drillstring_comp": pd.DataFrame(comp),
        "drillparam": pd.DataFrame(param),
        "formation": pd.DataFrame(form),
    }


def _report(report: list, idwell: str, idjob: str, ids: _Ids, day: dt.datetime) -> str:
    rid = ids("D")
    report.append({"idwell": idwell, "idrecparent": idjob, "idrec": rid, "dttmend": day + dt.timedelta(hours=23, minutes=59),
                   "dttmstart": day, "plannextrptops": "continue", "rpttmactops": "drilling", "summaryops": "ok"})
    return rid


def _tl(idwell, rep, code1, code2, code4, frac, bore, seq, opscat, com, ids) -> dict:
    return {"idwell": idwell, "idrecparent": rep, "idrec": ids("T"), "code1": f" {code1} ", "code2": code2.lower(),
            "code3": "x", "code4": code4, "com": com, "duration": frac, "idrecwellbore": bore,
            "opscategory": str(opscat), "sysseq": seq}


def build_tables(seed: int = 7) -> dict[str, dict[str, pd.DataFrame]]:
    """``{database: {dataset: DataFrame}}`` for the per-table query mode."""
    rng, ids = np.random.default_rng(seed), _Ids()
    return {db: _database(db, wells, rng, ids) for db, wells in _WORLD.items()}


def write_csv_dataset(out_dir: Path, seed: int = 7) -> None:
    out_dir = Path(out_dir)
    tables = build_tables(seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"name": ["master", "tempdb"] + list(tables)}).to_csv(out_dir / "databases.csv", index=False)
    for db, datasets in tables.items():
        if not any(len(df) for df in datasets.values()):
            continue
        (out_dir / db).mkdir(exist_ok=True)
        for name, df in datasets.items():
            df.to_csv(out_dir / db / f"{name}.csv", index=False)
