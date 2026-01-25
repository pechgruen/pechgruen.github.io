#!/usr/bin/env node
/**
 * GEDCOM (Gramps) -> minimal JSON for a Pechgrün GED browser:
 * - people.json (id -> person)
 * - families.json (id -> family)
 * - surnames.json (sorted unique surnames)
 * - surnameToPersons.json (surname -> sorted person ids)
 * - import-report.json (counts + warnings)
 *
 * Whitelist tags only; ignore the rest safely.
 *
 * to run script from project directory root: scripts/ged-to-json.mjs ~/Desktop/test.ged public/data/ged
 */

import fs from "node:fs";
import path from "node:path";
import readline from "node:readline";

const INPUT = process.argv[2] || "test.ged";
const OUTDIR = process.argv[3] || "public/data/ged";

function ensureDir(p) {
  fs.mkdirSync(p, { recursive: true });
}

function stripXref(x) {
  // "@I123@" -> "I123"
  return typeof x === "string" ? x.replace(/^@|@$/g, "") : null;
}

function parseLine(line) {
  // GEDCOM line: <level> [@XREF@] <TAG> [VALUE]
  const m = line.match(/^(\d+)\s+(?:(@[^@]+@)\s+)?([A-Z0-9_]+)(?:\s+(.*))?$/);
  if (!m) return null;
  return {
    level: Number(m[1]),
    xref: m[2] || null,
    tag: m[3],
    value: (m[4] ?? "").trim(),
  };
}

/**
 * Display vs. Key:
 * - surnameDisplay: keep as-is (trim + collapse spaces)
 * - surnameKey: uppercase key only for grouping (case-insensitive)
 */
function surnameDisplay(s) {
  if (!s) return "";
  return String(s).trim().replace(/\s+/g, " ");
}

function surnameKey(s) {
  return surnameDisplay(s).toUpperCase();
}

function normalizePlace(s) {
  if (!s) return "";
  return s.trim().replace(/\s+/g, " ");
}

// --- ADDITIVE: GEDCOM date normalization (display-only) ---
const GED_MONTH = {
  JAN: "01",
  FEB: "02",
  MAR: "03",
  APR: "04",
  MAY: "05",
  JUN: "06",
  JUL: "07",
  AUG: "08",
  SEP: "09",
  OCT: "10",
  NOV: "11",
  DEC: "12",
};

function normalizeGedcomDateDisplay(dateStr) {
  if (!dateStr) return null;
  const s0 = String(dateStr).trim().replace(/\s+/g, " ");
  if (!s0) return null;

  // Qualifier handling (only ABT/BEF, per your constraints)
  let prefix = "";
  let s = s0;

  const qm = s.match(/^(ABT|BEF)\s+(.*)$/i);
  if (qm) {
    const q = qm[1].toUpperCase();
    s = (qm[2] || "").trim();
    if (q === "ABT") prefix = "ca. ";
    else if (q === "BEF") prefix = "vor ";
  }

  // Try to parse: [DD] MON YYYY  (DD optional)
  const m = s.match(/^(?:(\d{1,2})\s+)?([A-Z]{3})\s+(\d{4})$/i);
  if (m) {
    const dayRaw = m[1] ? Number(m[1]) : null;
    const monKey = m[2].toUpperCase();
    const year = m[3];

    const mm = GED_MONTH[monKey];
    if (!mm) return prefix ? prefix + s : s0;

    if (dayRaw != null && Number.isFinite(dayRaw) && dayRaw >= 1 && dayRaw <= 31) {
      const dd = String(dayRaw).padStart(2, "0");
      return `${prefix}${dd}.${mm}.${year}`;
    }
    return `${prefix}${mm}.${year}`;
  }

  const y = s.match(/^(\d{4})$/);
  if (y) return `${prefix}${y[1]}`;

  return prefix ? prefix + s : s0;
}
// --- END ADDITIVE ---

function extractYear(dateStr) {
  const m = dateStr.match(/(\d{4})/);
  return m ? Number(m[1]) : null;
}

function pickPrimaryName(names) {
  // Prefer the NAME without TYPE married (Gramps usually exports married name as TYPE married)
  if (!Array.isArray(names) || names.length === 0) return null;
  const notMarried = names.find((n) => (n.type || "").toLowerCase() !== "married");
  return notMarried || names[0];
}

function localeCompareDE(a, b) {
  return a.localeCompare(b, "de", { sensitivity: "base" });
}

async function main() {
  ensureDir(OUTDIR);

  const people = new Map(); // id -> raw person
  const families = new Map(); // id -> raw family

  const report = {
    inputFile: INPUT,
    outputDir: OUTDIR,
    counts: { individuals: 0, families: 0 },
    ignoredTagsTop: {},
    warnings: {
      brokenRefs: 0,
      externalRefs: 0,
      notes:
        "External refs are expected in a Pechgrün subset; broken refs indicate malformed GED or parsing issues.",
    },
    parseErrors: 0,
    examples: {
      brokenRefSamples: [],
    },
  };

  const ignoredTags = new Map(); // tag -> count

  // Current record state
  let currentType = null; // "INDI" | "FAM" | null
  let currentId = null;

  let currentPerson = null;
  let currentFamily = null;

  let currentEvent = null; // "BIRT" | "DEAT" | "MARR" | null
  let currentName = null;

  // NEW: capture custom facts/events inside INDI, for Hausname etc.
  let currentCustom = null; // { tag: "EVEN"|"FACT", rawValue, type, data }

  function finalizeCustomForPerson() {
    if (!currentPerson || !currentCustom) return;

    const type = (currentCustom.type || "").trim();
    if (/^hausname$/i.test(type)) {
      // In your GED export, Hausname is stored as: 1 EVEN Brüln / 2 TYPE Hausname
      // But be robust: sometimes the actual value is in VALUE/NOTE instead.
      const val =
        (currentCustom.data && String(currentCustom.data).trim()) ||
        (currentCustom.rawValue && String(currentCustom.rawValue).trim()) ||
        "";

      if (val) currentPerson.houseName = val;
    }

    currentCustom = null;
  }

  function flushCurrent() {
    // finalize any pending custom event
    finalizeCustomForPerson();

    if (currentType === "INDI" && currentPerson && currentId) {
      people.set(currentId, currentPerson);
      report.counts.individuals += 1;
    } else if (currentType === "FAM" && currentFamily && currentId) {
      families.set(currentId, currentFamily);
      report.counts.families += 1;
    }
    currentType = null;
    currentId = null;
    currentPerson = null;
    currentFamily = null;
    currentEvent = null;
    currentName = null;
    currentCustom = null;
  }

  const rl = readline.createInterface({
    input: fs.createReadStream(INPUT, { encoding: "utf8" }),
    crlfDelay: Infinity,
  });

  for await (const line of rl) {
    const rec = parseLine(line);
    if (!rec) {
      report.parseErrors += 1;
      continue;
    }

    // Start of a new record
    if (rec.level === 0) {
      // close out any open NAME
      if (currentType === "INDI" && currentPerson && currentName) {
        currentPerson.names.push(currentName);
        currentName = null;
      }
      flushCurrent();

      // Identify record
      if (rec.tag === "INDI" && rec.xref) {
        currentType = "INDI";
        currentId = stripXref(rec.xref);
        currentPerson = {
          id: currentId,
          names: [],
          sex: null,
          birth: { date: null, place: null, year: null },
          death: { date: null, place: null, year: null },
          occupation: null,
          famc: [],
          fams: [],
          // NEW:
          nickname: null,   // from NAME.NICK or NICK tag
          houseName: null,  // from custom fact/event TYPE Hausname
        };
      } else if (rec.tag === "FAM" && rec.xref) {
        currentType = "FAM";
        currentId = stripXref(rec.xref);
        currentFamily = {
          id: currentId,
          husband: null,
          wife: null,
          children: [],
          marriage: { date: null, place: null, year: null },
        };
      } else {
        currentType = null;
        currentId = null;
      }
      continue;
    }

    if (!currentType) continue;

    // --- INDI parsing (whitelist) ---
    if (currentType === "INDI") {
      // If we hit any new level-1 tag, a pending custom event should be finalized
      if (rec.level === 1 && currentCustom && rec.tag !== "TYPE" && rec.tag !== "NOTE" && rec.tag !== "VALUE") {
        finalizeCustomForPerson();
      }

      // Begin new NAME at level 1
      if (rec.level === 1 && rec.tag === "NAME") {
        if (currentName) currentPerson.names.push(currentName);
        currentName = {
          raw: rec.value || null,
          givn: null,
          surn: null,
          type: null,
          // NEW:
          nick: null,
        };
        currentEvent = null;
        currentCustom = null;
        continue;
      }

      // If we see any new level-1 tag (BIRT/DEAT/FAMC/...), the NAME block is finished.
      if (rec.level === 1 && currentName && rec.tag !== "NAME") {
        currentPerson.names.push(currentName);

        // NEW: persist nickname (prefer NICK from the primary NAME if present)
        if (currentName.nick && !currentPerson.nickname) {
          currentPerson.nickname = currentName.nick;
        }

        currentName = null;
      }

      // NAME subfields at level 2
      if (rec.level === 2 && currentName) {
        if (rec.tag === "GIVN") currentName.givn = rec.value || null;
        else if (rec.tag === "SURN") currentName.surn = rec.value || null;
        else if (rec.tag === "TYPE") currentName.type = rec.value || null;
        // NEW: NICK inside NAME (as in your test.ged)
        else if (rec.tag === "NICK") {
          currentName.nick = rec.value || null;
          if (rec.value && !currentPerson.nickname) currentPerson.nickname = rec.value;
        } else {
          ignoredTags.set(rec.tag, (ignoredTags.get(rec.tag) || 0) + 1);
        }
        continue;
      }

      // Also accept top-level NICK (some exporters use it)
      if (rec.level === 1 && rec.tag === "NICK") {
        currentPerson.nickname = rec.value || currentPerson.nickname;
        currentEvent = null;
        currentCustom = null;
        continue;
      }

      // NEW: capture custom facts/events (Hausname)
      if (rec.level === 1 && (rec.tag === "EVEN" || rec.tag === "FACT")) {
        // start a new custom record; value may be on the same line (as in "1 EVEN Brüln")
        currentCustom = {
          tag: rec.tag,
          rawValue: rec.value || "",
          type: null,
          data: null, // VALUE/NOTE (if present)
        };
        currentEvent = null;
        continue;
      }
      if (rec.level === 2 && currentCustom) {
        if (rec.tag === "TYPE") currentCustom.type = rec.value || null;
        else if (rec.tag === "VALUE") currentCustom.data = rec.value || null;
        else if (rec.tag === "NOTE") currentCustom.data = rec.value || null;
        else {
          ignoredTags.set(rec.tag, (ignoredTags.get(rec.tag) || 0) + 1);
        }
        continue;
      }

      // Core fields
      if (rec.level === 1 && rec.tag === "SEX") {
        currentPerson.sex = rec.value || null;
        currentEvent = null;
        currentCustom = null;
        continue;
      }
      if (rec.level === 1 && rec.tag === "OCCU") {
        currentPerson.occupation = rec.value || null;
        currentEvent = null;
        currentCustom = null;
        continue;
      }
      if (rec.level === 1 && rec.tag === "FAMC") {
        currentPerson.famc.push(stripXref(rec.value));
        currentEvent = null;
        currentCustom = null;
        continue;
      }
      if (rec.level === 1 && rec.tag === "FAMS") {
        currentPerson.fams.push(stripXref(rec.value));
        currentEvent = null;
        currentCustom = null;
        continue;
      }

      // Events
      if (rec.level === 1 && (rec.tag === "BIRT" || rec.tag === "DEAT")) {
        currentEvent = rec.tag;
        currentCustom = null;
        continue;
      }
      if (rec.level === 2 && currentEvent) {
        if (rec.tag === "DATE") {
          if (currentEvent === "BIRT") {
            currentPerson.birth.date = normalizeGedcomDateDisplay(rec.value) || null;
            currentPerson.birth.year = extractYear(rec.value);
          } else if (currentEvent === "DEAT") {
            currentPerson.death.date = normalizeGedcomDateDisplay(rec.value) || null;
            currentPerson.death.year = extractYear(rec.value);
          }
        } else if (rec.tag === "PLAC") {
          if (currentEvent === "BIRT") currentPerson.birth.place = normalizePlace(rec.value);
          else if (currentEvent === "DEAT") currentPerson.death.place = normalizePlace(rec.value);
        } else {
          ignoredTags.set(rec.tag, (ignoredTags.get(rec.tag) || 0) + 1);
        }
        continue;
      }

      ignoredTags.set(rec.tag, (ignoredTags.get(rec.tag) || 0) + 1);
      continue;
    }

    // --- FAM parsing (whitelist) ---
    if (currentType === "FAM") {
      if (rec.level === 1 && rec.tag === "HUSB") {
        currentFamily.husband = stripXref(rec.value);
        currentEvent = null;
        continue;
      }
      if (rec.level === 1 && rec.tag === "WIFE") {
        currentFamily.wife = stripXref(rec.value);
        currentEvent = null;
        continue;
      }
      if (rec.level === 1 && rec.tag === "CHIL") {
        currentFamily.children.push(stripXref(rec.value));
        currentEvent = null;
        continue;
      }
      if (rec.level === 1 && rec.tag === "MARR") {
        currentEvent = "MARR";
        continue;
      }
      if (rec.level === 2 && currentEvent === "MARR") {
        if (rec.tag === "DATE") {
          currentFamily.marriage.date = normalizeGedcomDateDisplay(rec.value) || null;
          currentFamily.marriage.year = extractYear(rec.value);
        } else if (rec.tag === "PLAC") {
          currentFamily.marriage.place = normalizePlace(rec.value);
        } else {
          ignoredTags.set(rec.tag, (ignoredTags.get(rec.tag) || 0) + 1);
        }
        continue;
      }

      ignoredTags.set(rec.tag, (ignoredTags.get(rec.tag) || 0) + 1);
      continue;
    }
  }

  // Flush last record
  if (currentType === "INDI" && currentPerson && currentName) {
    currentPerson.names.push(currentName);
    if (currentName.nick && !currentPerson.nickname) currentPerson.nickname = currentName.nick;
    currentName = null;
  }
  flushCurrent();

  // Post-process: choose primary name + build indices + validate refs
  const peopleOut = {};
  const familiesOut = {};

  const personIds = new Set(people.keys());
  const familyIds = new Set(families.keys());

  // Convert persons
  for (const [id, p] of people.entries()) {
    const primary = pickPrimaryName(p.names);
    const given = primary?.givn || null;

    const surnRaw = primary?.surn || null;

    let surnameIndex = surnRaw;
    let displaySurname = surnRaw;
    let legBirthSurname = null;
    let legNewSurname = null;

    if (typeof surnRaw === "string") {
      const m = surnRaw.match(/^\s*(.+?)\s*,\s*leg\.\s*(.+?)\s*$/i);
      if (m) {
        legBirthSurname = (m[1] || "").trim();
        legNewSurname = (m[2] || "").trim();
        if (legNewSurname) {
          surnameIndex = legNewSurname;
          displaySurname = `${legNewSurname} (leg.)`;
        }
      }
    }

    const displayName =
      given && displaySurname
        ? `${given} ${displaySurname}`
        : primary?.raw
          ? primary.raw.replace(/\//g, "").trim()
          : id;

    for (const f of p.famc) {
      if (!f) continue;
      if (!familyIds.has(f)) report.warnings.externalRefs += 1;
    }
    for (const f of p.fams) {
      if (!f) continue;
      if (!familyIds.has(f)) report.warnings.externalRefs += 1;
    }

    peopleOut[id] = {
      id,
      name: {
        given,
        surname: surnameIndex || null,
        display: displayName,
        ...(legBirthSurname ? { legBirthSurname } : {}),
        ...(legNewSurname ? { legNewSurname } : {}),
        ...(surnRaw ? { surnameRaw: surnRaw } : {}),
      },
      sex: p.sex,
      birth: p.birth,
      death: p.death,
      occupation: p.occupation,
      famc: p.famc.filter(Boolean),
      fams: p.fams.filter(Boolean),

      // NEW: export these for the website / GED-browser
      nickname: p.nickname || null,
      houseName: p.houseName || null,
    };
  }

  // Convert families
  for (const [id, f] of families.entries()) {
    for (const pid of [f.husband, f.wife, ...(f.children || [])]) {
      if (!pid) continue;
      if (!personIds.has(pid)) report.warnings.externalRefs += 1;
    }

    familiesOut[id] = {
      id,
      husband: f.husband,
      wife: f.wife,
      children: (f.children || []).filter(Boolean),
      marriage: f.marriage,
    };
  }

  // Build surname index
  const keyToIds = new Map();
  const keyToDisplay = new Map();

  for (const [id, p] of Object.entries(peopleOut)) {
    const disp = surnameDisplay(p.name.surname || "");
    const key = disp ? surnameKey(disp) : "(UNKNOWN)";

    if (!keyToIds.has(key)) keyToIds.set(key, []);
    keyToIds.get(key).push(id);

    if (key !== "(UNKNOWN)" && !keyToDisplay.has(key) && disp) {
      keyToDisplay.set(key, disp);
    }
  }

  // Sort persons within surname
  for (const [k, ids] of keyToIds.entries()) {
    ids.sort((a, b) => {
      const pa = peopleOut[a];
      const pb = peopleOut[b];
      const ga = (pa?.name?.given || "").trim();
      const gb = (pb?.name?.given || "").trim();
      const c1 = localeCompareDE(ga, gb);
      if (c1 !== 0) return c1;

      const ya = pa?.birth?.year ?? 9999;
      const yb = pb?.birth?.year ?? 9999;
      if (ya !== yb) return ya - yb;

      return localeCompareDE(pa?.name?.display || a, pb?.name?.display || b);
    });
  }

  const surnames = Array.from(keyToIds.keys())
    .map((k) => {
      if (k === "(UNKNOWN)") return "(UNKNOWN)";
      return keyToDisplay.get(k) || k;
    })
    .sort(localeCompareDE);

  const surnameToPersons = {};
  for (const disp of surnames) {
    if (disp === "(UNKNOWN)") {
      surnameToPersons["(UNKNOWN)"] = keyToIds.get("(UNKNOWN)") || [];
      continue;
    }
    const k = surnameKey(disp);
    surnameToPersons[disp] = keyToIds.get(k) || [];
  }

  fs.writeFileSync(path.join(OUTDIR, "people.json"), JSON.stringify(peopleOut, null, 2), "utf8");
  fs.writeFileSync(path.join(OUTDIR, "families.json"), JSON.stringify(familiesOut, null, 2), "utf8");
  fs.writeFileSync(path.join(OUTDIR, "surnames.json"), JSON.stringify(surnames, null, 2), "utf8");
  fs.writeFileSync(
    path.join(OUTDIR, "surnameToPersons.json"),
    JSON.stringify(surnameToPersons, null, 2),
    "utf8"
  );

  const ignoredArr = Array.from(ignoredTags.entries()).sort((a, b) => b[1] - a[1]);
  report.ignoredTagsTop = Object.fromEntries(ignoredArr.slice(0, 30));

  fs.writeFileSync(path.join(OUTDIR, "import-report.json"), JSON.stringify(report, null, 2), "utf8");

  console.log(`✅ Wrote JSON to ${OUTDIR}`);
  console.log(`   people:   ${Object.keys(peopleOut).length}`);
  console.log(`   families: ${Object.keys(familiesOut).length}`);
  console.log(`   surnames: ${surnames.length}`);
  console.log(`   report:   import-report.json`);
}

main().catch((err) => {
  console.error("❌ Import failed:", err);
  process.exit(1);
});
