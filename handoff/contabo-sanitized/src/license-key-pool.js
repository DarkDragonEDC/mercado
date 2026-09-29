import { createLicense, getLicense, getLicenseStats } from "./license-store.js";

// Mantem a interface usada pelo fluxo de pagamentos, agora sem dependencia do Gist.
export async function reserveLicenseKey({ sourceId, discordUserId, username = "", paymentId, planId = "", planName = "", modules, days }) {
  const record = await createLicense({
    sourceId,
    discordUserId,
    username,
    paymentId,
    planId,
    planName,
    modules,
    days,
    note: planName ? `Compra automática do plano ${planName}` : ""
  });
  return {
    sourceId,
    paymentId: String(paymentId || ""),
    discordUserId,
    licenseKey: record.licenseKey,
    status: "reserved",
    reservedAt: record.createdAt,
    expiresAt: record.expiresAt,
    licenseId: record.id,
    existing: Boolean(record.existing)
  };
}

export async function claimFreeTrial({ discordUserId, days = 1 }) {
  const sourceId = `free-trial:${String(discordUserId)}`;
  return createLicense({
    sourceId,
    discordUserId,
    days,
    maxDevices: 1,
    note: "Teste gratis utilizado uma unica vez por usuario do Discord",
    actor: "free-trial"
  });
}

export async function getReservation(sourceId) {
  const record = await getLicense(sourceId, { reveal: true });
  if (!record) return null;
  return { ...record, sourceId, status: "reserved", reservedAt: record.createdAt };
}

export async function getKeyPoolStats() {
  const stats = await getLicenseStats();
  return { ...stats, available: "ilimitado", used: stats.total, duplicateKeys: 0, invalid: 0 };
}
