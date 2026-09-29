import crypto from "node:crypto";
import { chmod, mkdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";
import { config } from "./config.js";

const dataDir = path.resolve("data");
const dataFile = path.join(dataDir, "licenses.json");
let queue = Promise.resolve();

export const LICENSE_MODULES = Object.freeze({
  PURCHASE: "purchase_orders",
  SALES: "sales_orders"
});

const SUPPORTED_MODULES = new Set(Object.values(LICENSE_MODULES));

export function modulesForAccess(access) {
  return {
    purchase: [LICENSE_MODULES.PURCHASE],
    sales: [LICENSE_MODULES.SALES],
    complete: [LICENSE_MODULES.PURCHASE, LICENSE_MODULES.SALES]
  }[String(access || "").trim().toLowerCase()] || [LICENSE_MODULES.PURCHASE];
}

export function formatLicenseModules(modules) {
  const normalized = normalizeModules(modules);
  if (normalized.length === 2) return "Compra + Venda (Ciclo Automatico)";
  if (normalized[0] === LICENSE_MODULES.SALES) return "Venda";
  return "Compra";
}

function normalizeModules(modules) {
  const normalized = [...new Set((Array.isArray(modules) ? modules : [])
    .map((item) => String(item).trim().toLowerCase())
    .filter((item) => SUPPORTED_MODULES.has(item)))];
  return normalized.length ? normalized : [LICENSE_MODULES.PURCHASE];
}

function serialized(operation) {
  const result = queue.then(operation, operation);
  queue = result.catch(() => {});
  return result;
}

function emptyStore() {
  return { version: 1, licenses: {}, sourceIndex: {}, audit: [] };
}

async function loadStore() {
  try {
    const parsed = JSON.parse(await readFile(dataFile, "utf8"));
    return { ...emptyStore(), ...parsed };
  } catch (error) {
    if (error.code === "ENOENT") return emptyStore();
    throw error;
  }
}

async function saveStore(store) {
  await mkdir(dataDir, { recursive: true });
  const temporary = `${dataFile}.tmp`;
  await writeFile(temporary, JSON.stringify(store, null, 2), "utf8");
  await chmod(temporary, 0o600);
  await rename(temporary, dataFile);
}

function secretBuffer() {
  const value = String(config.licenseEncryptionKey || "");
  if (!/^[a-f0-9]{64}$/i.test(value)) {
    throw new Error("LICENSE_ENCRYPTION_KEY deve possuir 64 caracteres hexadecimais.");
  }
  return Buffer.from(value, "hex");
}

function normalizeKey(value) {
  return String(value || "").trim().toUpperCase();
}

function keyHash(value) {
  return crypto.createHmac("sha256", config.licensePepper).update(normalizeKey(value)).digest("hex");
}

function deviceHash(value) {
  return crypto.createHmac("sha256", config.licensePepper).update(`device:${String(value || "").trim()}`).digest("hex");
}

function encryptKey(value) {
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv("aes-256-gcm", secretBuffer(), iv);
  const encrypted = Buffer.concat([cipher.update(normalizeKey(value), "utf8"), cipher.final()]);
  return {
    encryptedKey: encrypted.toString("base64"),
    encryptionIv: iv.toString("base64"),
    encryptionTag: cipher.getAuthTag().toString("base64")
  };
}

function decryptKey(record) {
  const decipher = crypto.createDecipheriv(
    "aes-256-gcm",
    secretBuffer(),
    Buffer.from(record.encryptionIv, "base64")
  );
  decipher.setAuthTag(Buffer.from(record.encryptionTag, "base64"));
  return Buffer.concat([
    decipher.update(Buffer.from(record.encryptedKey, "base64")),
    decipher.final()
  ]).toString("utf8");
}

function generateKey() {
  const alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  const groups = Array.from({ length: 4 }, () =>
    Array.from({ length: 5 }, () => alphabet[crypto.randomInt(alphabet.length)]).join("")
  );
  return `ALBIONMKT-${groups.join("-")}`;
}

function addDays(base, days) {
  return new Date(new Date(base).getTime() + Number(days) * 86_400_000).toISOString();
}

function publicRecord(record) {
  const now = Date.now();
  const expired = new Date(record.expiresAt).getTime() <= now;
  return {
    id: record.id,
    keyPrefix: record.keyPrefix,
    discordUserId: record.discordUserId,
    username: record.username || "",
    planId: record.planId || "",
    planName: record.planName || "",
    sourceId: record.sourceId,
    paymentId: record.paymentId,
    status: record.status,
    effectiveStatus: record.status === "active" && expired ? "expired" : record.status,
    createdAt: record.createdAt,
    expiresAt: record.expiresAt,
    maxDevices: record.maxDevices,
    modules: normalizeModules(record.modules),
    devices: record.devices || [],
    note: record.note || "",
    updatedAt: record.updatedAt
  };
}

function audit(store, action, record, actor = "system", detail = "") {
  store.audit.push({ at: new Date().toISOString(), action, licenseId: record.id, actor, detail });
  if (store.audit.length > 5000) store.audit = store.audit.slice(-5000);
}

function findRecord(store, identifier) {
  const normalized = String(identifier || "").trim();
  if (store.licenses[normalized]) return store.licenses[normalized];
  const upper = normalized.toUpperCase();
  return Object.values(store.licenses).find((item) =>
    item.sourceId === normalized || item.keyPrefix.toUpperCase() === upper || item.keyHash === keyHash(upper)
  ) || null;
}

export function createLicense({ sourceId = "", paymentId = "", discordUserId = "", username = "", planId = "", planName = "", days = config.accessDays, maxDevices = 1, modules = [LICENSE_MODULES.PURCHASE], note = "", actor = "system", licenseKey = "", startsAt = new Date().toISOString() }) {
  return serialized(async () => {
    const store = await loadStore();
    if (sourceId && store.sourceIndex[sourceId]) {
      const existing = store.licenses[store.sourceIndex[sourceId]];
      return { ...publicRecord(existing), licenseKey: decryptKey(existing), existing: true };
    }

    let generated = normalizeKey(licenseKey || generateKey());
    while (Object.values(store.licenses).some((item) => item.keyHash === keyHash(generated))) {
      if (licenseKey) throw new Error("Esta key ja esta cadastrada.");
      generated = generateKey();
    }
    const now = new Date().toISOString();
    const id = crypto.randomUUID();
    const record = {
      id,
      keyHash: keyHash(generated),
      keyPrefix: `${generated.slice(0, 14)}...${generated.slice(-5)}`,
      ...encryptKey(generated),
      discordUserId: String(discordUserId || ""),
      username: String(username || "").slice(0, 100),
      planId: String(planId || "").slice(0, 40),
      planName: String(planName || "").slice(0, 100),
      sourceId: String(sourceId || ""),
      paymentId: String(paymentId || ""),
      status: "active",
      createdAt: now,
      startsAt,
      expiresAt: addDays(startsAt, Math.max(1, Number(days) || config.accessDays)),
      maxDevices: Math.max(1, Math.min(10, Number(maxDevices) || 1)),
      modules: normalizeModules(modules),
      devices: [],
      note: String(note || "").slice(0, 500),
      updatedAt: now
    };
    store.licenses[id] = record;
    if (record.sourceId) store.sourceIndex[record.sourceId] = id;
    audit(store, "created", record, actor, record.note);
    await saveStore(store);
    return { ...publicRecord(record), licenseKey: generated, existing: false };
  });
}

export async function getLicense(identifier, { reveal = false } = {}) {
  const record = findRecord(await loadStore(), identifier);
  if (!record) return null;
  return { ...publicRecord(record), ...(reveal ? { licenseKey: decryptKey(record) } : {}) };
}

export async function listLicenses() {
  const store = await loadStore();
  return Object.values(store.licenses).map(publicRecord).sort((a, b) => b.createdAt.localeCompare(a.createdAt));
}

export async function getLicenseStats() {
  const records = await listLicenses();
  const now = Date.now();
  const soon = now + 7 * 86_400_000;
  return {
    total: records.length,
    active: records.filter((item) => item.effectiveStatus === "active").length,
    expiring: records.filter((item) => item.effectiveStatus === "active" && new Date(item.expiresAt).getTime() <= soon).length,
    expired: records.filter((item) => item.effectiveStatus === "expired").length,
    revoked: records.filter((item) => item.status === "revoked").length,
    devices: records.reduce((sum, item) => sum + item.devices.length, 0)
  };
}

export function updateLicense(identifier, action, { days = 0, reason = "", actor = "system", modules = [] } = {}) {
  return serialized(async () => {
    const store = await loadStore();
    const record = findRecord(store, identifier);
    if (!record) return null;
    if (action === "extend") {
      const base = Math.max(Date.now(), new Date(record.expiresAt).getTime());
      record.expiresAt = addDays(base, Math.max(1, Number(days) || 1));
    } else if (action === "revoke") {
      record.status = "revoked";
      record.revokedReason = String(reason || "Revogada pelo administrador").slice(0, 500);
    } else if (action === "reactivate") {
      record.status = "active";
      record.revokedReason = "";
      if (new Date(record.expiresAt).getTime() <= Date.now()) record.expiresAt = addDays(new Date(), Math.max(1, Number(days) || config.accessDays));
    } else if (action === "reset-devices") {
      record.devices = [];
    } else if (action === "set-modules") {
      record.modules = normalizeModules(modules);
    } else {
      throw new Error("Acao de licenca invalida.");
    }
    record.updatedAt = new Date().toISOString();
    audit(store, action, record, actor, reason || (days ? `${days} dias` : ""));
    await saveStore(store);
    return publicRecord(record);
  });
}

export function validateLicense({ licenseKey, hwid, appVersion = "", activate = false }) {
  return serialized(async () => {
    const store = await loadStore();
    const record = findRecord(store, licenseKey);
    if (!record) return { valid: false, code: "INVALID_KEY", message: "Licenca invalida." };
    if (record.status !== "active") return { valid: false, code: "REVOKED", message: "Licenca revogada." };
    const remainingSeconds = Math.floor((new Date(record.expiresAt).getTime() - Date.now()) / 1000);
    if (remainingSeconds <= 0) return { valid: false, code: "EXPIRED", message: "Licenca expirada.", expiresAt: record.expiresAt, remainingSeconds: 0 };
    if (!String(hwid || "").trim()) return { valid: false, code: "HWID_REQUIRED", message: "Identificador do computador ausente." };

    const hashed = deviceHash(hwid);
    let device = record.devices.find((item) => item.hwidHash === hashed);
    let newlyActivated = false;
    if (!device) {
      if (!activate) return { valid: false, code: "NOT_ACTIVATED", message: "Computador ainda nao ativado." };
      if (record.devices.length >= record.maxDevices) return { valid: false, code: "DEVICE_LIMIT", message: "Limite de computadores atingido." };
      device = { hwidHash: hashed, firstSeenAt: new Date().toISOString(), lastSeenAt: new Date().toISOString(), appVersion: String(appVersion || "").slice(0, 50) };
      record.devices.push(device);
      newlyActivated = true;
      audit(store, "device-activated", record, "api", `dispositivo ${record.devices.length}`);
    } else if (Date.now() - new Date(device.lastSeenAt).getTime() >= 5 * 60_000) {
      device.lastSeenAt = new Date().toISOString();
      device.appVersion = String(appVersion || device.appVersion || "").slice(0, 50);
    }
    record.updatedAt = new Date().toISOString();
    await saveStore(store);
    return { valid: true, code: "OK", message: "Licenca valida.", expiresAt: record.expiresAt, remainingSeconds, newlyActivated, maxDevices: record.maxDevices, activeDevices: record.devices.length, modules: normalizeModules(record.modules) };
  });
}

async function readJson(file, fallback) {
  try { return JSON.parse(await readFile(file, "utf8")); } catch (error) { if (error.code === "ENOENT") return fallback; throw error; }
}

export async function migrateLegacyLicenses() {
  const reservations = await readJson(path.join(dataDir, "license-key-reservations.json"), {});
  const sales = await readJson(path.join(dataDir, "sales.json"), {});
  let imported = 0;
  for (const legacy of Object.values(reservations)) {
    if (!legacy.licenseKey || legacy.status === "released") continue;
    const sale = sales[legacy.sourceId] || {};
    const startsAt = sale.paidAt || legacy.reservedAt || new Date().toISOString();
    const days = sale.expiresAt
      ? Math.max(1, Math.ceil((new Date(sale.expiresAt).getTime() - new Date(startsAt).getTime()) / 86_400_000))
      : config.accessDays;
    const result = await createLicense({ sourceId: legacy.sourceId, paymentId: legacy.paymentId, discordUserId: legacy.discordUserId, days, startsAt, licenseKey: legacy.licenseKey, note: "Importada do sistema anterior", actor: "migration" });
    if (!result.existing) imported += 1;
  }
  for (const sale of Object.values(sales)) {
    if (!sale.licenseKey || sale.licenseKey === "-" || sale.licenseKey === config.genericLicenseKey || sale.licenseKey.includes("...")) continue;
    const startsAt = sale.paidAt || sale.updatedAt || new Date().toISOString();
    const days = sale.expiresAt
      ? Math.max(1, Math.ceil((new Date(sale.expiresAt).getTime() - new Date(startsAt).getTime()) / 86_400_000))
      : config.accessDays;
    try {
      const result = await createLicense({ sourceId: sale.sourceId, paymentId: sale.paymentId, discordUserId: sale.discordUserId, days, startsAt, licenseKey: sale.licenseKey, note: "Importada do controle de vendas anterior", actor: "migration" });
      if (!result.existing) imported += 1;
    } catch (error) {
      if (!/ja esta cadastrada/i.test(error.message)) throw error;
    }
  }
  return imported;
}
