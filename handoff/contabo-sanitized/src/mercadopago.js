import crypto from "node:crypto";
import { config } from "./config.js";
import {
  buildCommercialReference,
  parseCommercialReference,
  requireCommercialPlan
} from "./commercial-plans.js";

async function mpRequest(path, options = {}) {
  const response = await fetch(`https://api.mercadopago.com${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${config.mercadoPagoToken}`,
      "Content-Type": "application/json",
      ...options.headers
    }
  });

  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(`Mercado Pago ${response.status}: ${JSON.stringify(body)}`);
  }
  return body;
}

export function buildSubscriptionPayload({ discordUserId, email }) {
  const externalReference = `discord:${config.guildId}:${discordUserId}`;
  const recurring = config.mercadoPagoPlanId
    ? { preapproval_plan_id: config.mercadoPagoPlanId }
    : {
        auto_recurring: {
          frequency: 1,
          frequency_type: "months",
          transaction_amount: config.planPrice,
          currency_id: config.currency
        }
      };
  return {
    ...recurring,
    reason: config.planName,
    external_reference: externalReference,
    payer_email: email,
    back_url: `${config.publicBaseUrl}/retorno`,
    notification_url: `${config.publicBaseUrl}/webhooks/mercadopago`,
    status: "pending"
  };
}

export function createSubscription({ discordUserId, email }) {
  return mpRequest("/preapproval", {
    method: "POST",
    body: JSON.stringify(buildSubscriptionPayload({ discordUserId, email }))
  });
}

export function buildPaymentPreferencePayload({ discordUserId, email, planId, purchaseId }) {
  const plan = requireCommercialPlan(planId);
  const externalReference = buildCommercialReference({
    guildId: config.guildId,
    discordUserId,
    planId: plan.id,
    purchaseId
  });
  return {
    items: [
      {
        id: `albionmkt-${plan.id}`,
        title: `${plan.name} — AlbionMKT`,
        description: `${plan.description} ${plan.days} dias de acesso.`,
        quantity: 1,
        currency_id: plan.currency,
        unit_price: plan.price
      }
    ],
    payer: { email },
    external_reference: externalReference,
    metadata: {
      discord_user_id: String(discordUserId),
      guild_id: String(config.guildId),
      plan: plan.id,
      purchase_id: String(purchaseId)
    },
    payment_methods: {
      default_payment_method_id: "pix"
    },
    notification_url: `${config.publicBaseUrl}/webhooks/mercadopago?source=checkout-pro`,
    back_urls: {
      success: `${config.publicBaseUrl}/retorno?status=approved`,
      pending: `${config.publicBaseUrl}/retorno?status=pending`,
      failure: `${config.publicBaseUrl}/retorno?status=failure`
    },
    auto_return: "approved"
  };
}

export function createPaymentPreference({ discordUserId, email, planId, purchaseId }) {
  return mpRequest("/checkout/preferences", {
    method: "POST",
    body: JSON.stringify(buildPaymentPreferencePayload({ discordUserId, email, planId, purchaseId }))
  });
}

export function getSubscription(id) {
  return mpRequest(`/preapproval/${encodeURIComponent(id)}`);
}

export function getPayment(id) {
  return mpRequest(`/v1/payments/${encodeURIComponent(id)}`);
}

export function getAuthorizedPayment(id) {
  return mpRequest(`/authorized_payments/${encodeURIComponent(id)}`);
}

export function getAuthorizedPaymentsBySubscription(preapprovalId) {
  const query = new URLSearchParams({ preapproval_id: String(preapprovalId) });
  return mpRequest(`/authorized_payments/search?${query}`);
}

export function getAuthorizedPaymentsByPayment(paymentId) {
  const query = new URLSearchParams({ payment_id: String(paymentId) });
  return mpRequest(`/authorized_payments/search?${query}`);
}

export function getRecentPayments(limit = 20) {
  const query = new URLSearchParams({
    sort: "date_created",
    criteria: "desc",
    limit: String(limit)
  });
  return mpRequest(`/v1/payments/search?${query}`);
}

export function parseDiscordReference(reference) {
  const commercial = parseCommercialReference(reference);
  if (commercial) return commercial;
  const match = /^discord:(\d+):(\d+)$/.exec(reference || "");
  return match ? { guildId: match[1], discordUserId: match[2], legacy: true } : null;
}

export function verifyWebhook(req) {
  if (!config.webhookSecret) return false;
  const signature = req.get("x-signature") || "";
  const requestId = req.get("x-request-id") || "";
  const parts = Object.fromEntries(
    signature.split(",").map((part) => part.trim().split("="))
  );
  const dataId = String(req.query["data.id"] || req.body?.data?.id || "").toLowerCase();
  if (!parts.ts || !parts.v1 || !dataId) return false;

  const manifest = `id:${dataId};request-id:${requestId};ts:${parts.ts};`;
  const expected = crypto
    .createHmac("sha256", config.webhookSecret)
    .update(manifest)
    .digest("hex");

  const supplied = Buffer.from(parts.v1, "hex");
  const calculated = Buffer.from(expected, "hex");
  return supplied.length === calculated.length && crypto.timingSafeEqual(supplied, calculated);
}
