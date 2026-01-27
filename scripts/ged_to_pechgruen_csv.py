#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
GED -> public/data/pechgruen-ged.csv

Inclusion (who gets exported):
Include a person if ANY of these is true:
  1) Birthplace contains "Pechgrün" or "Neuhäuser"
  2) Deathplace contains "Pechgrün" or "Neuhäuser"
  3) Person is a spouse of someone who satisfies (1) or (2)

House-ID (Haus) heuristic (priority):
  A) If Birthplace has Pechgrün/Neuhäuser -> use that (P### / N###, missing number -> P000/N000)
  B) Special: if A gives P000/N000 and Deathplace is same locale with a number -> use Death number
  C) Else if Deathplace has Pechgrün/Neuhäuser -> use that (P### / N###, missing number -> P000/N000)
  D) Else spouse-fallback both ways: use spouse's house if available
  E) Else "?"

Special:
  - If place contains "Wehrmühle" -> house code is K### (usually K027). (Place text stays unchanged.)
  - Empty fields -> "?" except Bemerkungen stays empty.
  - Names:
      * Prefer a NAME block whose TYPE is NOT "married" for birth name.
      * Within a NAME block, prefer 2 SURN / 2 GIVN over slash parsing.
      * Normalize surname:
            - "... legitimiert X" / "leg. X" -> X
            - remove stray parentheses: "(Richter)" "Richter)" "(Richter" -> "Richter"
            - if after normalization nothing remains -> "?"
      * Female unknown maiden marker "... m." -> "?"
  - Family name:
      * Male: birth surname
      * Female: husband's birth surname if available, else her birth surname

Date formatting:
  - "27 FEB 1936" -> "27.02.1936"
  - "ABT 1795"    -> "ca. 1795"
  - "MAY 1863"    -> "05.1863"
  - "1863"        -> "1863"
  - otherwise keep as-is

Usage:
  python3 scripts/ged_to_pechgruen_csv.py --in ~/desktop/test.ged --out public/data/pechgruen-ged.csv --sort
"""

import argparse
import csv
import re
from pathlib import Path
from typing import Dict, Any, Optional, List, Set


MONTHS = {
    "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04", "MAY": "05", "JUN": "06",
    "JUL": "07", "AUG": "08", "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12"
}

LEG_RE = re.compile(r"\b(leg\.?|legitimiert|legit\.?)\b", re.IGNORECASE)
UNKNOWN_MAIDEN_RE = re.compile(r"^\.\.\.\s*m\.\s*", re.IGNORECASE)

P_RE = re.compile(r"\bPechgrün\b", re.IGNORECASE)
N_RE = re.compile(r"\bNeuhäuser\b", re.IGNORECASE)
WEHRMUEHLE_RE = re.compile(r"Wehrmühle", re.IGNORECASE)
NUM_RE = re.compile(r"#\s*([0-9]{1,3})", re.IGNORECASE)


def norm_xref(s: str) -> str:
    return s.strip().strip("@")


def qmark(x: Optional[str]) -> str:
    t = (x or "").strip()
    return t if t else "?"


def strip_parens(s: str) -> str:
    if not s:
        return s
    t = s.strip()
    t = t.lstrip("()").rstrip("()").strip()
    return t


def normalize_surname(raw: str) -> str:
    if not raw:
        return ""
    s = raw.strip()

    # legitimiert -> use surname after marker
    m = LEG_RE.search(s)
    if m:
        after = s[m.end():].strip().lstrip(" .:,-")
        s = after if after else s

    s = strip_parens(s)
    return s.strip()


def fmt_date(raw: Optional[str]) -> str:
    if not raw:
        return "?"
    s = raw.strip()
    if not s:
        return "?"
    up = s.upper()

    if up.startswith("ABT"):
        m = re.search(r"\d{4}", up)
        return f"ca. {m.group(0)}" if m else "?"

    m = re.match(r"(\d{1,2})\s+([A-Z]{3})\s+(\d{4})", up)
    if m:
        day = f"{int(m.group(1)):02d}"
        mon = MONTHS.get(m.group(2), "??")
        return f"{day}.{mon}.{m.group(3)}"

    m = re.match(r"([A-Z]{3})\s+(\d{4})", up)
    if m:
        mon = MONTHS.get(m.group(1), "??")
        return f"{mon}.{m.group(2)}"

    m = re.match(r"(\d{4})$", up)
    if m:
        return m.group(1)

    return s

def sort_date_key(s: str):
    """
    Convert date strings to sortable tuples.
    Order: (year, month, day)
    Unknown or malformed dates go to the end.
    """
    if not s or s == "?":
        return (9999, 12, 31)

    t = s.strip().lower()

    # ca. yyyy
    if t.startswith("ca."):
        try:
            y = int(t.replace("ca.", "").strip())
            return (y, 0, 0)
        except ValueError:
            return (9999, 12, 31)

    # dd.mm.yyyy
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", t)
    if m:
        return (int(m.group(3)), int(m.group(2)), int(m.group(1)))

    # mm.yyyy
    m = re.match(r"(\d{2})\.(\d{4})", t)
    if m:
        return (int(m.group(2)), int(m.group(1)), 0)

    # yyyy
    m = re.match(r"(\d{4})$", t)
    if m:
        return (int(m.group(1)), 0, 0)

    return (9999, 12, 31)

def place_to_code(place: Optional[str]) -> Optional[str]:
    if not place:
        return None
    s = place.strip()
    if not s or s == "?":
        return None

    # Wehrmühle is Kösteldorf (K)
    if WEHRMUEHLE_RE.search(s):
        m = NUM_RE.search(s)
        num = int(m.group(1)) if m else 27
        return f"K{num:03d}"

    if P_RE.search(s):
        m = NUM_RE.search(s)
        num = int(m.group(1)) if m else 0
        return f"P{num:03d}"

    if N_RE.search(s):
        m = NUM_RE.search(s)
        num = int(m.group(1)) if m else 0
        return f"N{num:03d}"

    return None


def best_house_code(birth_place: Optional[str], death_place: Optional[str]) -> Optional[str]:
    """
    House priority between birth/death when both are P/N/K:
    - If same locale and birth is 000 and death has number -> use death
    - If locale differs (P vs N vs K) -> prefer birth
    - Else birth
    """
    b = place_to_code(birth_place)
    d = place_to_code(death_place)

    if b and d:
        if b[0] == d[0] and b[1:] == "000" and d[1:] != "000":
            return d
        if b[0] != d[0]:
            return b
        return b

    return b or d


def parse_ged(path: Path):
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()

    indi: Dict[str, Dict[str, Any]] = {}
    fam: Dict[str, Dict[str, str]] = {}

    current_type = None
    current_id = None
    current_event = None
    current_name = None  # active NAME block

    def finish_name_block(p: Dict[str, Any]):
        nonlocal current_name
        if current_name is not None:
            p["names"].append(current_name)
            current_name = None

    for line in lines:
        if line.startswith("0 "):
            current_event = None
            parts = line.split()
            current_type = None
            current_id = None

            if len(parts) >= 3 and parts[1].startswith("@") and parts[2] in ("INDI", "FAM"):
                current_id = norm_xref(parts[1])
                current_type = parts[2]

                if current_type == "INDI":
                    indi[current_id] = {
                        "id": current_id,
                        "sex": "",
                        "names": [],        # list of {given, surn, type}
                        "birth_date": "",
                        "birth_place": "",
                        "death_date": "",
                        "death_place": "",
                        "remarks": "",
                        "fams": [],         # spouse family links
                    }
                    current_name = None
                else:
                    fam[current_id] = {"id": current_id, "husb": "", "wife": ""}
            continue

        if not current_type or not current_id:
            continue

        parts = line.split(" ", 2)
        if len(parts) < 2:
            continue
        level, tag = parts[0], parts[1]
        value = parts[2] if len(parts) == 3 else ""

        if current_type == "INDI":
            p = indi[current_id]

            if level == "1":
                if tag != "NAME":
                    finish_name_block(p)
                current_event = None

                if tag == "NAME":
                    finish_name_block(p)

                    # fallback parse from slash form
                    given, surn = "", ""
                    if "/" in value:
                        pieces = value.split("/")
                        given = pieces[0].strip()
                        surn = pieces[1].strip() if len(pieces) > 1 else ""
                    else:
                        given = value.strip()
                        surn = ""

                    current_name = {"given": given, "surn": surn, "type": None}

                elif tag == "SEX":
                    p["sex"] = value.strip()

                elif tag in ("BIRT", "DEAT"):
                    current_event = tag

                elif tag == "OCCU":
                    occ = value.strip()
                    if occ:
                        p["remarks"] = (p["remarks"] + "; " if p["remarks"] else "") + occ

                elif tag == "FAMS":
                    fid = norm_xref(value.strip())
                    if fid:
                        p["fams"].append(fid)

            elif level == "2":
                # NAME sub-tags
                if current_name is not None:
                    if tag == "TYPE":
                        current_name["type"] = value.strip()
                    elif tag == "GIVN" and value.strip():
                        current_name["given"] = value.strip()
                    elif tag == "SURN" and value.strip():
                        current_name["surn"] = value.strip()

                # Event sub-tags
                if current_event == "BIRT":
                    if tag == "DATE":
                        p["birth_date"] = value.strip()
                    elif tag == "PLAC":
                        p["birth_place"] = value.strip()
                elif current_event == "DEAT":
                    if tag == "DATE":
                        p["death_date"] = value.strip()
                    elif tag == "PLAC":
                        p["death_place"] = value.strip()

        else:
            f = fam[current_id]
            if level == "1":
                if tag == "HUSB":
                    f["husb"] = norm_xref(value.strip())
                elif tag == "WIFE":
                    f["wife"] = norm_xref(value.strip())

    # finalize birth-name selection per person
    for p in indi.values():
        names: List[Dict[str, Any]] = p["names"]
        chosen = None

        # prefer non-married type
        for n in names:
            t = (n.get("type") or "").strip().lower()
            if t != "married":
                chosen = n
                break
        if chosen is None and names:
            chosen = names[0]

        given = (chosen.get("given") if chosen else "") or ""
        raw_surn = (chosen.get("surn") if chosen else "") or ""

        given = given.strip()
        raw_surn = raw_surn.strip()

        if (p.get("sex") or "").upper() == "F" and UNKNOWN_MAIDEN_RE.search(raw_surn):
            birth_surn = "?"
        else:
            birth_surn = normalize_surname(raw_surn)
            birth_surn = birth_surn if birth_surn else "?"

        p["given_final"] = given if given else "?"
        p["birth_surname_final"] = birth_surn

    return indi, fam


def family_surname_for(indi: Dict[str, Dict[str, Any]], fam: Dict[str, Dict[str, str]], pid: str) -> str:
    p = indi[pid]
    sex = (p.get("sex") or "").upper()
    birth_surn = p.get("birth_surname_final") or "?"

    if sex == "M":
        return birth_surn

    if sex == "F":
        # husband's birth surname if available
        for fid in p.get("fams", []):
            f = fam.get(fid)
            if not f:
                continue
            if f.get("wife") == pid and f.get("husb"):
                husb = indi.get(f["husb"])
                if husb:
                    hs = husb.get("birth_surname_final") or "?"
                    if hs != "?":
                        return hs
        return birth_surn

    return birth_surn


def spouse_house_fallback(indi: Dict[str, Dict[str, Any]], fam: Dict[str, Dict[str, str]], pid: str) -> Optional[str]:
    p = indi.get(pid)
    if not p:
        return None

    for fid in p.get("fams", []):
        f = fam.get(fid)
        if not f:
            continue

        spouse_id = None
        if f.get("husb") == pid and f.get("wife"):
            spouse_id = f["wife"]
        elif f.get("wife") == pid and f.get("husb"):
            spouse_id = f["husb"]

        if spouse_id and spouse_id in indi:
            sp = indi[spouse_id]
            # spouse's house is derived from birth/death with same rules
            code = house_for(indi, fam, spouse_id, _allow_spouse_fallback=False)
            if code and code != "?":
                return code

    return None


def house_for(
    indi: Dict[str, Dict[str, Any]],
    fam: Dict[str, Dict[str, str]],
    pid: str,
    _allow_spouse_fallback: bool = True
) -> str:
    """
    Implements the agreed house priority:
      A) birth if P/N/K
      B) if birth is 000 and death same locale numbered -> death
      C) else death if P/N/K
      D) spouse fallback
      E) ?
    """
    p = indi.get(pid)
    if not p:
        return "?"

    bp = p.get("birth_place", "")
    dp = p.get("death_place", "")

    # A/B handled by best_house_code when both exist
    bcode = place_to_code(bp)
    dcode = place_to_code(dp)

    if bcode:
        # Special B: if birth is 000 and death same locale numbered
        if dcode and bcode[0] == dcode[0] and bcode[1:] == "000" and dcode[1:] != "000":
            return dcode
        return bcode

    if dcode:
        return dcode

    if _allow_spouse_fallback:
        sp = spouse_house_fallback(indi, fam, pid)
        if sp:
            return sp

    return "?"


def should_include_person(pid: str, indi: Dict[str, Dict[str, Any]]) -> bool:
    p = indi[pid]
    bp = (p.get("birth_place") or "").strip()
    dp = (p.get("death_place") or "").strip()
    return bool(P_RE.search(bp) or N_RE.search(bp) or P_RE.search(dp) or N_RE.search(dp))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True, help="Input GED file")
    ap.add_argument("--out", dest="out", required=True, help="Output CSV file")
    ap.add_argument("--sort", action="store_true", help="Sort output by Haus/Familienname/Vornamen")
    args = ap.parse_args()

    in_path = Path(args.inp).expanduser()
    out_path = Path(args.out)

    indi, fam = parse_ged(in_path)

    # Determine base included set (birth or death in P/N)
    base_included: Set[str] = {pid for pid in indi.keys() if should_include_person(pid, indi)}

    # Add spouses of included persons (rule 3)
    spouse_added: Set[str] = set()
    for pid in list(base_included):
        p = indi.get(pid)
        if not p:
            continue
        for fid in p.get("fams", []):
            f = fam.get(fid)
            if not f:
                continue
            husb = f.get("husb")
            wife = f.get("wife")
            if husb and husb in indi and husb not in base_included:
                spouse_added.add(husb)
            if wife and wife in indi and wife not in base_included:
                spouse_added.add(wife)

    included: Set[str] = base_included.union(spouse_added)

    rows = []
    for pid in included:
        p = indi[pid]

        haus = house_for(indi, fam, pid)
        fam_name = family_surname_for(indi, fam, pid)

        row = {
            "Haus": qmark(haus),
            "Familienname": qmark(fam_name),
            "Geburtsname": qmark(p.get("birth_surname_final") or "?"),
            "Vornamen": qmark(p.get("given_final") or "?"),
            "Geburtsdatum": fmt_date(p.get("birth_date", "")),
            "Geburtsort": qmark(p.get("birth_place", "")),
            "Sterbedatum": fmt_date(p.get("death_date", "")),
            "Sterbeort": qmark(p.get("death_place", "")),
            "Bemerkungen": (p.get("remarks") or "").strip(),
        }
        rows.append(row)

    if args.sort:
        rows.sort(key=lambda r: (r["Haus"], sort_date_key(r["Geburtsdatum"]), r["Familienname"], r["Vornamen"]))

    # add Zeile and write
    header = ["Zeile","Haus","Familienname","Geburtsname","Vornamen","Geburtsdatum","Geburtsort","Sterbedatum","Sterbeort","Bemerkungen"]
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header, quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        for i, r in enumerate(rows, start=1):
            r2 = dict(r)
            r2["Zeile"] = str(i)
            # fill ? except Bemerkungen
            for k in header:
                if k == "Bemerkungen":
                    r2[k] = r2.get(k, "")
                else:
                    r2[k] = qmark(r2.get(k, ""))
            w.writerow({k: r2.get(k, "") for k in header})


if __name__ == "__main__":
    main()
