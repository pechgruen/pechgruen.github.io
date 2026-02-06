#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MyHeritage GEDCOM (full) -> filtered GEDCOM subset (temporary), for the Pechgrün GED browser.

Selection logic (validated vs Gramps in your tests):

Base persons:
  - BIRT/DEAT.PLAC contains 'Pechgrün' OR 'Neuhäuser'
  OR
  - custom event/fact with TYPE == 'Bookmark'   (under 1 EVEN or 1 FACT)

Then expand:
  - 1-hop from base persons:
      parents (via FAMC -> FAM -> HUSB/WIFE)
      siblings (all CHIL of that FAMC family)
      spouses (via each FAMS family: the other partner)
      shared children (via each FAMS family: CHIL)
  - parent-FAMS closure for EVERY person in the set:
      for each person -> parents -> all FAMS families of each parent
      include partners + children in those parent families
      (NO recursion into the spouse's other families)

Finally filter by birth year:
  - BIRT/DATE must contain a year (4 digits)
  - year must be between 1500 and 1948 (inclusive)
  - qualifiers like ABT/BEF/AFT etc. are fine; we just extract the year

Output subset GEDCOM contains:
  - HEAD (always kept)
  - selected INDI records
  - selected FAM records
  - TRLR (always kept)
"""

import sys
import re
from typing import Dict, List, Optional, Set, Tuple

TARGETS = ["Pechgrün", "Neuhäuser"]
TARGETS_CF = [t.casefold() for t in TARGETS]

BOOKMARK_TYPE = "Bookmark"

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

# Relationship indices (by stripped IDs)
FAMC: Dict[str, str] = {}          # person -> family id (child family)
FAMS: Dict[str, List[str]] = {}    # person -> [family ids] (spouse families)

HUSB: Dict[str, str] = {}          # family -> husband person id
WIFE: Dict[str, str] = {}          # family -> wife person id
CHIL: Dict[str, List[str]] = {}    # family -> [child person ids]

BIRTH_YEAR: Dict[str, int] = {}    # person -> birth year
HAS_BOOKMARK: Set[str] = set()     # persons that have Bookmark type

def parse_indices_and_base(ged_path: str) -> Tuple[Set[str], Set[str]]:
    """
    One pass over GEDCOM to build indices and compute:
      - base:     persons with (place_hit OR bookmark_hit)
      - place_base: persons with place_hit only (Pechgrün/Neuhäuser in BIRT/DEAT.PLAC)

    We will later add spouses of place_base persons to the seed set,
    but NOT spouses of bookmark-only persons.
    """
    base: Set[str] = set()
    place_base: Set[str] = set()

    current_rec_type: Optional[str] = None  # INDI / FAM / other
    current_id: Optional[str] = None        # stripped id: "I123" or "F45"

    in_birt = False
    in_deat = False
    in_custom = False  # inside EVEN/FACT

    place_hit = False
    bookmark_hit = False

    def finalize_person(pid: Optional[str]):
        nonlocal place_hit, bookmark_hit
        if pid:
            if place_hit:
                place_base.add(pid)
            if place_hit or bookmark_hit:
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

                # 0 @I123@ INDI  / 0 @F45@ FAM
                if xref and tag in ("INDI", "FAM"):
                    current_rec_type = tag
                    current_id = strip_xref(xref)
                    if tag == "FAM" and current_id:
                        CHIL.setdefault(current_id, [])
                continue

            # -------- INDI --------
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
                    # leaving blocks
                    in_birt = in_deat = False
                    if tag not in ("EVEN", "FACT"):
                        in_custom = False

                # place hit in birth/death
                if level == 2 and tag == "PLAC" and (in_birt or in_deat):
                    if contains_target(value):
                        place_hit = True
                    continue

                # birth year
                if level == 2 and tag == "DATE" and in_birt:
                    y = extract_year(value)
                    if y:
                        BIRTH_YEAR[current_id] = y
                    continue

                # bookmark event/fact type
                if level == 2 and tag == "TYPE" and in_custom:
                    if value.casefold() == BOOKMARK_TYPE.casefold():
                        HAS_BOOKMARK.add(current_id)
                        bookmark_hit = True
                    continue

                # family links
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

            # -------- FAM --------
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

    return base, place_base


def expand_1hop(base: Set[str]) -> Set[str]:
    out: Set[str] = set(base)

    for p in base:
        # parents + siblings via FAMC
        famc = FAMC.get(p)
        if famc:
            for par in (HUSB.get(famc), WIFE.get(famc)):
                if par:
                    out.add(par)
            for sib in CHIL.get(famc, []):
                if sib:
                    out.add(sib)

        # spouses + shared children via FAMS
        for fams in FAMS.get(p, []):
            for spouse in (HUSB.get(fams), WIFE.get(fams)):
                if spouse and spouse != p:
                    out.add(spouse)
            for ch in CHIL.get(fams, []):
                if ch:
                    out.add(ch)

    return out

def add_parent_fams_closure(person_set: Set[str], triggers: Set[str]) -> Set[str]:
    """
    Parent-FAMS closure, but ONLY for trigger persons (Seeds).

    For each trigger person:
      person -> parents via FAMC
      for each parent -> all their FAMS families
      add partners + children from those parent families

    This prevents the "one hub too far" expansion (e.g. showing parents/siblings
    of an external parent that was only pulled in to enable half-siblings).
    """
    out: Set[str] = set(person_set)

    for p in triggers:
        # Only apply closure for triggers that are actually present in the current set
        if p not in person_set:
            continue

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
                if h:
                    out.add(h)
                if w:
                    out.add(w)

                for ch in CHIL.get(fams, []):
                    if ch:
                        out.add(ch)

    return out

def birth_year_ok(pid: str) -> bool:
    y = BIRTH_YEAR.get(pid)
    return y is not None and YEAR_MIN <= y <= YEAR_MAX

def compute_selected_people(ged_path: str) -> Set[str]:
    base, place_base = parse_indices_and_base(ged_path)

    # NEW: add spouses of PLACE-based seeds (Pechgrün/Neuhäuser via BIRT/DEAT.PLAC)
    # to the seed set. Do NOT do this for bookmark-only seeds.
    for p in place_base:
        for fams in FAMS.get(p, []):
            for spouse in (HUSB.get(fams), WIFE.get(fams)):
                if spouse and spouse != p:
                    base.add(spouse)

    s1 = expand_1hop(base)
    s2 = add_parent_fams_closure(s1, base)  # triggers = seeds only (now incl. spouses-of-place-seeds)
    return {pid for pid in s2 if birth_year_ok(pid)}

def compute_selected_families(people_ids: Set[str]) -> Set[str]:
    fams_out: Set[str] = set()

    # families referenced by selected people
    for pid in people_ids:
        famc = FAMC.get(pid)
        if famc:
            fams_out.add(famc)
        for fam in FAMS.get(pid, []):
            fams_out.add(fam)

    # plus families where selected people appear as HUSB/WIFE/CHIL
    for fam_id, kids in CHIL.items():
        if (HUSB.get(fam_id) in people_ids) or (WIFE.get(fam_id) in people_ids):
            fams_out.add(fam_id)
            continue
        for ch in kids:
            if ch in people_ids:
                fams_out.add(fam_id)
                break

    return fams_out

def write_subset(in_path: str, out_path: str, keep_people: Set[str], keep_fams: Set[str]) -> Tuple[int, int]:
    """
    Stream-copy records:
      keep HEAD, TRLR always
      keep INDI if id in keep_people
      keep FAM  if id in keep_fams

    Additionally, drop malformed non-GEDCOM lines inside kept records
    (e.g. raw HTML lines like "<p ...>" without leading "2 CONC/CONT ...").
    """
    kept_indi = 0
    kept_fam = 0
    dropped_non_ged_lines = 0

    # Accept lines that start with optional whitespace + GEDCOM level digit(s) + space.
    # (Some exporters may have leading spaces; GEDCOM normally doesn't, but this is harmless.)
    GED_LINE_OK = re.compile(r"^\s*\d+\s")

    def parse0(line: str) -> Tuple[Optional[str], Optional[str]]:
        m = re.match(r"^0\s+(?:(@[^@]+@)\s+)?([A-Z0-9_]+)(?:\s+.*)?$", line)
        if not m:
            return None, None
        xref = m.group(1)
        tag = m.group(2)
        rid = strip_xref(xref) if xref else None
        return tag, rid

    with open(in_path, "r", encoding="utf-8", errors="replace") as fin, open(out_path, "w", encoding="utf-8") as fout:
        buffer: List[str] = []
        cur_tag: Optional[str] = None
        cur_id: Optional[str] = None

        def flush():
            nonlocal kept_indi, kept_fam, dropped_non_ged_lines, buffer, cur_tag, cur_id
            if not buffer:
                return

            keep = False
            if cur_tag in ("HEAD", "TRLR"):
                keep = True
            elif cur_tag == "INDI" and cur_id and cur_id in keep_people:
                keep = True
                kept_indi += 1
            elif cur_tag == "FAM" and cur_id and cur_id in keep_fams:
                keep = True
                kept_fam += 1

            if keep:
                for ln in buffer:
                    if GED_LINE_OK.match(ln):
                        fout.write(ln + "\n")
                    else:
                        dropped_non_ged_lines += 1

            buffer = []

        for raw in fin:
            line = raw.rstrip("\n")
            if line.startswith("0 "):
                if buffer:
                    flush()
                buffer = [line]
                cur_tag, cur_id = parse0(line)
            else:
                buffer.append(line)

        if buffer:
            flush()

    print("   dropped non-GED lines:", dropped_non_ged_lines)
    return kept_indi, kept_fam

def main():
    if len(sys.argv) != 3:
        print("Usage: python3 scripts/mh-filter-subset.py /path/to/MyHeritage.ged /tmp/pechgruen-subset.ged", file=sys.stderr)
        sys.exit(2)

    in_ged = sys.argv[1]
    out_ged = sys.argv[2]

    keep_people = compute_selected_people(in_ged)
    keep_fams = compute_selected_families(keep_people)

    kept_indi, kept_fam = write_subset(in_ged, out_ged, keep_people, keep_fams)

    print("✅ subset written:", out_ged)
    print("   people kept:", kept_indi)
    print("   families kept:", kept_fam)
    print("   bookmark people:", len(HAS_BOOKMARK))

if __name__ == "__main__":
    main()
