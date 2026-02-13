#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import re
import sys
from typing import Dict, List, Optional, Set

TARGETS = ["Pechgrün", "Neuhäuser"]
TARGETS_CF = [t.casefold() for t in TARGETS]

BOOKMARK_TYPE = "Bookmark"  # 2 TYPE Bookmark under 1 EVEN/FACT

YEAR_MIN = 1500
YEAR_MAX = 1948

LINE_RE = re.compile(r"^(\d+)\s+(@[^@]+@\s+)?([A-Z0-9_]+)(?:\s+(.*))?$")
YEAR_RE = re.compile(r"\b(\d{4})\b")

def contains_target(text: str) -> bool:
    if not text:
        return False
    t = text.casefold()
    return any(x in t for x in TARGETS_CF)

def extract_year(date_str: str) -> Optional[int]:
    if not date_str:
        return None
    m = YEAR_RE.search(date_str)
    return int(m.group(1)) if m else None

def strip_xref(x: str) -> Optional[str]:
    if not x:
        return None
    x = x.strip()
    if x.startswith("@") and x.endswith("@"):
        return x[1:-1]
    return x

FAMC: Dict[str, str] = {}
FAMS: Dict[str, List[str]] = {}
HUSB: Dict[str, str] = {}
WIFE: Dict[str, str] = {}
CHIL: Dict[str, List[str]] = {}

BIRTH_YEAR: Dict[str, int] = {}
HAS_BOOKMARK: Set[str] = set()

def parse_indices_and_base(ged_path: str) -> Set[str]:
    base: Set[str] = set()

    current_rec_type: Optional[str] = None
    current_id: Optional[str] = None

    in_birt = False
    in_deat = False
    in_custom = False

    place_hit = False
    bookmark_hit = False

    def finalize_person(pid: Optional[str]):
        nonlocal place_hit, bookmark_hit
        if pid and (place_hit or bookmark_hit):
            base.add(pid)
        place_hit = False
        bookmark_hit = False

    with open(ged_path, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.rstrip("\n")
            m = LINE_RE.match(line)
            if not m:
                continue

            level = int(m.group(1))
            xref = (m.group(2) or "").strip()
            tag = m.group(3)
            value = (m.group(4) or "").strip()

            if level == 0:
                if current_rec_type == "INDI":
                    finalize_person(current_id)

                in_birt = in_deat = in_custom = False
                current_rec_type = None
                current_id = None

                if xref and tag in ("INDI", "FAM"):
                    current_rec_type = tag
                    current_id = strip_xref(xref)
                    if tag == "FAM" and current_id:
                        CHIL.setdefault(current_id, [])
                continue

            if current_rec_type == "INDI" and current_id:
                if level == 1 and tag == "BIRT":
                    in_birt, in_deat, in_custom = True, False, False
                    continue
                if level == 1 and tag == "DEAT":
                    in_birt, in_deat, in_custom = False, True, False
                    continue
                if level == 1 and tag in ("EVEN", "FACT"):
                    in_birt = in_deat = False
                    in_custom = True
                    continue
                if level == 1:
                    in_birt = in_deat = False
                    if tag not in ("EVEN", "FACT"):
                        in_custom = False

                if level == 2 and tag == "PLAC" and (in_birt or in_deat):
                    if contains_target(value):
                        place_hit = True
                    continue

                if level == 2 and tag == "DATE" and in_birt:
                    y = extract_year(value)
                    if y:
                        BIRTH_YEAR[current_id] = y
                    continue

                if level == 2 and tag == "TYPE" and in_custom:
                    if value.casefold() == BOOKMARK_TYPE.casefold():
                        HAS_BOOKMARK.add(current_id)
                        bookmark_hit = True
                    continue

                if level == 1 and tag == "FAMC":
                    fam = strip_xref(value)
                    if fam:
                        FAMC[current_id] = fam
                    continue
                if level == 1 and tag == "FAMS":
                    fam = strip_xref(value)
                    if fam:
                        FAMS.setdefault(current_id, []).append(fam)
                    continue

            elif current_rec_type == "FAM" and current_id:
                if level == 1 and tag == "HUSB":
                    pid = strip_xref(value)
                    if pid:
                        HUSB[current_id] = pid
                    continue
                if level == 1 and tag == "WIFE":
                    pid = strip_xref(value)
                    if pid:
                        WIFE[current_id] = pid
                    continue
                if level == 1 and tag == "CHIL":
                    pid = strip_xref(value)
                    if pid:
                        CHIL.setdefault(current_id, []).append(pid)
                    continue

    if current_rec_type == "INDI":
        finalize_person(current_id)

    return base

def expand_1hop(base: Set[str]) -> Set[str]:
    out: Set[str] = set(base)
    for p in base:
        famc = FAMC.get(p)
        if famc:
            for par in (HUSB.get(famc), WIFE.get(famc)):
                if par:
                    out.add(par)
            for sib in CHIL.get(famc, []):
                if sib:
                    out.add(sib)

        for fams in FAMS.get(p, []):
            for spouse in (HUSB.get(fams), WIFE.get(fams)):
                if spouse and spouse != p:
                    out.add(spouse)
            for ch in CHIL.get(fams, []):
                if ch:
                    out.add(ch)
    return out

def add_parent_fams_closure(person_set: Set[str]) -> Set[str]:
    out: Set[str] = set(person_set)
    for p in list(person_set):
        famc = FAMC.get(p)
        if not famc:
            continue
        parents = [HUSB.get(famc), WIFE.get(famc)]
        for parent in parents:
            if not parent:
                continue
            out.add(parent)
            for fams in FAMS.get(parent, []):
                h = HUSB.get(fams)
                w = WIFE.get(fams)
                if h: out.add(h)
                if w: out.add(w)
                for ch in CHIL.get(fams, []):
                    if ch:
                        out.add(ch)
    return out

def birth_year_ok(pid: str) -> bool:
    y = BIRTH_YEAR.get(pid)
    return y is not None and YEAR_MIN <= y <= YEAR_MAX

def compute_selected_people(ged_path: str) -> Set[str]:
    base = parse_indices_and_base(ged_path)
    s1 = expand_1hop(base)
    s2 = add_parent_fams_closure(s1)
    return {pid for pid in s2 if birth_year_ok(pid)}

def compute_selected_families(people_ids: Set[str]) -> Set[str]:
    fams_out: Set[str] = set()

    for pid in people_ids:
        famc = FAMC.get(pid)
        if famc:
            fams_out.add(famc)
        for fam in FAMS.get(pid, []):
            fams_out.add(fam)

    for fam_id, kids in CHIL.items():
        if (HUSB.get(fam_id) in people_ids) or (WIFE.get(fam_id) in people_ids):
            fams_out.add(fam_id)
            continue
        for ch in kids:
            if ch in people_ids:
                fams_out.add(fam_id)
                break

    return fams_out

def main():
    if len(sys.argv) != 3:
        print("Usage: python3 scripts/select-ids.py /path/to/MyHeritage.ged /path/to/selected_ids.json", file=sys.stderr)
        sys.exit(2)

    ged_path = sys.argv[1]
    out_json = sys.argv[2]

    people_ids = compute_selected_people(ged_path)
    fam_ids = compute_selected_families(people_ids)

    payload = {
        "people": sorted(people_ids),
        "families": sorted(fam_ids),
        "meta": {
            "targets": TARGETS,
            "bookmarkType": BOOKMARK_TYPE,
            "birthYearMin": YEAR_MIN,
            "birthYearMax": YEAR_MAX,
            "peopleCount": len(people_ids),
            "familyCount": len(fam_ids),
            "bookmarkPeople": len(HAS_BOOKMARK),
        },
    }

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"✅ wrote {out_json}")
    print(f"   people:   {len(people_ids)}")
    print(f"   families: {len(fam_ids)}")
    print(f"   bookmarkPeople: {len(HAS_BOOKMARK)}")

if __name__ == "__main__":
    main()
