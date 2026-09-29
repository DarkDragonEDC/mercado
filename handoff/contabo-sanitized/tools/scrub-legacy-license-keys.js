import { chmod, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";

const dataDir = path.resolve(process.argv[2] || "data");
const licenses = JSON.parse(await readFile(path.join(dataDir, "licenses.json"), "utf8"));
let changed = 0;

for (const filename of ["license-key-reservations.json", "sales.json"]) {
  const target = path.join(dataDir, filename);
  let records;
  try {
    records = JSON.parse(await readFile(target, "utf8"));
  } catch (error) {
    if (error.code === "ENOENT") continue;
    throw error;
  }
  for (const record of Object.values(records)) {
    const id = licenses.sourceIndex[record.sourceId];
    const prefix = id ? licenses.licenses[id]?.keyPrefix : "";
    if (prefix && record.licenseKey !== prefix) {
      record.licenseKey = prefix;
      changed += 1;
    }
  }
  const temporary = `${target}.scrub.tmp`;
  await writeFile(temporary, JSON.stringify(records, null, 2), "utf8");
  await chmod(temporary, 0o600);
  await rename(temporary, target);
}

console.log(`LEGACY_KEYS_SCRUBBED=${changed}`);
