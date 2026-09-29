import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";

const dataDir = path.resolve("data");
const dataFile = path.join(dataDir, "subscriptions.json");
let queue = Promise.resolve();

async function loadAll() {
  try {
    return JSON.parse(await readFile(dataFile, "utf8"));
  } catch (error) {
    if (error.code === "ENOENT") return {};
    throw error;
  }
}

async function saveAll(data) {
  await mkdir(dataDir, { recursive: true });
  const temporary = `${dataFile}.tmp`;
  await writeFile(temporary, JSON.stringify(data, null, 2), "utf8");
  await rename(temporary, dataFile);
}

function serialized(operation) {
  const result = queue.then(operation, operation);
  queue = result.catch(() => {});
  return result;
}

export function saveSubscription(record) {
  return serialized(async () => {
    const all = await loadAll();
    all[record.preapprovalId] = {
      ...all[record.preapprovalId],
      ...record,
      updatedAt: new Date().toISOString()
    };
    await saveAll(all);
    return all[record.preapprovalId];
  });
}

export async function findByPreapprovalId(id) {
  const all = await loadAll();
  return all[id] || null;
}

export async function findByDiscordUser(userId) {
  const all = await loadAll();
  return Object.values(all).filter((item) => item.discordUserId === userId);
}

export async function findPendingStaticTests() {
  const all = await loadAll();
  return Object.values(all).filter(
    (item) => item.kind === "static_test" && !item.active && item.status === "pending"
  );
}

export async function findByPaymentId(paymentId) {
  const all = await loadAll();
  return Object.values(all).find((item) => String(item.paymentId || "") === String(paymentId)) || null;
}

export async function findByPurchaseId(purchaseId) {
  const all = await loadAll();
  return Object.values(all).find((item) => String(item.purchaseId || "") === String(purchaseId || "")) || null;
}

export async function listSubscriptions() {
  return Object.values(await loadAll());
}
