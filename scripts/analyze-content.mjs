import fs from "fs";
import path from "path";

const BASE_DIR = "./src/pages/texte";

const STOPWORDS = new Set([
  "nicht", "schon", "waren", "dieser", "wurde", "einem", "einen", "hatte",
  "konnte", "diese", "dabei", "durch", "später", "gegen", "unter", "wieder",
  "damals", "heute", "dann", "noch", "also", "seine", "ihren", "ihre",
  "seiner", "einer", "eines", "einem", "einen", "dass", "weil", "wobei",
  "oder", "auch", "beim", "über", "mehr", "sehr", "nach", "sich", "wird",
  "worden", "hat", "haben", "sein", "seine", "ihm", "ihn", "ihr", "ihre",
  "wie", "mit", "von", "aus", "den", "dem", "des", "die", "der", "das",
  "und", "ist", "im", "in", "am", "an", "zu", "auf", "für", "ein", "eine",
  "einer", "eines", "als", "bei", "man", "nur", "wenn", "doch", "hier",
  "there", "target", "blank", "noopener", "const", "return", "import", "export",
  "title", "subtitle", "chronik", "global", "length", "width", "margin",
  "padding", "color", "background", "font", "size", "line", "height",
  "max", "index", "intro", "author", "sourceshort", "safelabel"
]);

function stripFrontmatter(content) {
  return content.replace(/^---[\s\S]*?---/, "");
}

function stripStyleBlocks(content) {
  return content.replace(/<style[\s\S]*?<\/style>/gi, " ");
}

function stripScriptBlocks(content) {
  return content.replace(/<script[\s\S]*?<\/script>/gi, " ");
}

function stripAstroExpressions(content) {
  return content.replace(/\{[\s\S]*?\}/g, " ");
}

function stripTags(content) {
  return content.replace(/<[^>]+>/g, " ");
}

function extractWords(text) {
  return text.toLowerCase().match(/\b[a-zäöüß\-]{5,}\b/gi) || [];
}

function countWords(words) {
  const map = new Map();
  for (const word of words) {
    if (STOPWORDS.has(word)) continue;
    map.set(word, (map.get(word) || 0) + 1);
  }
  return map;
}

function topWords(map, limit = 12) {
  return [...map.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit);
}

function analyzeFile(filePath) {
  const raw = fs.readFileSync(filePath, "utf8");
  const cleaned = stripTags(
    stripAstroExpressions(
      stripScriptBlocks(
        stripStyleBlocks(
          stripFrontmatter(raw)
        )
      )
    )
  );

  const words = extractWords(cleaned);
  const counts = countWords(words);
  return topWords(counts);
}

function run() {
  const files = fs.readdirSync(BASE_DIR);

  for (const file of files) {
    if (!file.endsWith(".astro")) continue;

    const fullPath = path.join(BASE_DIR, file);
    const result = analyzeFile(fullPath);

    console.log(`\n=== ${file} ===`);
    for (const [word, count] of result) {
      console.log(`${word}: ${count}`);
    }
  }
}

run();