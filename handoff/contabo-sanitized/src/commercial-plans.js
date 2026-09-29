import crypto from "node:crypto";

export const COMMERCIAL_PLANS = Object.freeze([
  Object.freeze({
    id: "sales",
    name: "Venda",
    price: 39.90,
    currency: "BRL",
    days: 30,
    modules: Object.freeze(["sales_orders"]),
    description: "Venda os itens disponíveis na mochila."
  }),
  Object.freeze({
    id: "purchase",
    name: "Compra",
    price: 49.90,
    currency: "BRL",
    days: 30,
    modules: Object.freeze(["purchase_orders"]),
    description: "Criação contínua de ordens de compra."
  }),
  Object.freeze({
    id: "complete",
    name: "MKT Completo",
    price: 99.90,
    currency: "BRL",
    days: 30,
    modules: Object.freeze(["purchase_orders", "sales_orders"]),
    description: "Compra, coleta, venda e retorno automático às compras. Inclui a integração do ciclo completo."
  })
]);

const plansById = new Map(COMMERCIAL_PLANS.map((plan) => [plan.id, plan]));

export function getCommercialPlan(planId) {
  return plansById.get(String(planId || "").trim().toLowerCase()) || null;
}

export function requireCommercialPlan(planId) {
  const plan = getCommercialPlan(planId);
  if (!plan) throw new Error("Plano comercial inválido.");
  return plan;
}

export function createPurchaseId() {
  return crypto.randomUUID();
}

export function buildCommercialReference({ guildId, discordUserId, planId, purchaseId }) {
  const plan = requireCommercialPlan(planId);
  if (!/^\d+$/.test(String(guildId)) || !/^\d+$/.test(String(discordUserId))) {
    throw new Error("Identificação do Discord inválida.");
  }
  if (!/^[0-9a-f-]{36}$/i.test(String(purchaseId))) {
    throw new Error("Identificador interno da compra inválido.");
  }
  return `albionmkt:v1:${guildId}:${discordUserId}:${plan.id}:${purchaseId}`;
}

export function parseCommercialReference(reference) {
  const match = /^albionmkt:v1:(\d+):(\d+):(sales|purchase|complete):([0-9a-f-]{36})$/i.exec(String(reference || ""));
  if (!match) return null;
  return {
    guildId: match[1],
    discordUserId: match[2],
    planId: match[3].toLowerCase(),
    purchaseId: match[4].toLowerCase(),
    legacy: false
  };
}

export function validateCommercialPayment(payment, expectedGuildId) {
  const reference = parseCommercialReference(payment?.external_reference);
  if (!reference || reference.guildId !== String(expectedGuildId)) {
    return { ok: false, reason: "external_reference inválida" };
  }
  const plan = getCommercialPlan(reference.planId);
  const metadata = payment?.metadata || {};
  const checks = [
    [payment?.status === "approved", "status não aprovado"],
    [Number(payment?.transaction_amount) === plan.price, "valor divergente"],
    [payment?.currency_id === plan.currency, "moeda divergente"],
    [String(metadata.discord_user_id || "") === reference.discordUserId, "Discord user ID divergente"],
    [String(metadata.guild_id || "") === reference.guildId, "guild ID divergente"],
    [String(metadata.plan || "") === reference.planId, "plano divergente"],
    [String(metadata.purchase_id || "").toLowerCase() === reference.purchaseId, "compra divergente"]
  ];
  const failed = checks.find(([ok]) => !ok);
  return failed ? { ok: false, reason: failed[1], reference, plan } : { ok: true, reference, plan };
}

export function formatPlanPrice(plan) {
  return `R$ ${Number(plan.price).toFixed(2).replace(".", ",")}`;
}

export function requireLicenseReservation(reservation) {
  if (!reservation?.licenseKey) throw new Error("Nenhuma key pôde ser reservada para esta compra.");
  return reservation;
}
