import fs from "fs";
import path from "path";

// 1. Pfad zur Roh-HTML-Datei
const inputPath = path.resolve(
  "src/assets/texte/erinnerungen-karl-redelbach.html"
);

// 2. Ziel-JSON
const outputPath = path.resolve(
  "src/data/redelbach-mentions.json"
);

// 3. Datei lesen
const raw = fs.readFileSync(inputPath, "utf-8");

// 4. Personen-Makros finden: [[I500020|Name]]
const regex = /\[\[(I\d+)\|/g;

const counts = {};
let match;

while ((match = regex.exec(raw)) !== null) {
  const id = match[1];
  counts[id] = (counts[id] || 0) + 1;
}

// 5. JSON schreiben
fs.writeFileSync(outputPath, JSON.stringify(counts, null, 2));

console.log("✔ redelbach-mentions.json generated");