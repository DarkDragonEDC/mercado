import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";

const dataDir = path.resolve("data");
const dataFile = path.join(dataDir, "onboarding-acceptances.json");
let queue = Promise.resolve();

async function loadAll() {
  try {
    return JSON.parse(await readFile(dataFile, "utf8"));
  } catch (error) {
    if (error.code === "ENOENT") return {};
    throw error;
  }
}

export function saveOnboardingAcceptance(record) {
  const operation = queue.then(async () => {
    const all = await loadAll();
    all[record.discordUserId] = {
      ...all[record.discordUserId],
      ...record,
      acceptedAt: new Date().toISOString()
    };
    await mkdir(dataDir, { recursive: true });
    const temporary = `${dataFile}.tmp`;
    await writeFile(temporary, JSON.stringify(all, null, 2), "utf8");
    await rename(temporary, dataFile);
    return all[record.discordUserId];
  });
  queue = operation.catch(() => {});
  return operation;
}
