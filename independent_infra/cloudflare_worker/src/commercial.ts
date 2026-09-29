import { createLicense } from "./licensing";
import type { CommercialOrderRow, CommercialPlanId, Env, ModuleId } from "./types";

export interface CommercialPlan {
  id: CommercialPlanId;
  name: string;
  amountCents: number;
  modules: ModuleId[];
  roleEnv: "DISCORD_ROLE_COMPRA_ID" | "DISCORD_ROLE_VENDA_ID" | "DISCORD_ROLE_COMPLETO_ID";
}

export const COMMERCIAL_PLANS: Record<CommercialPlanId, CommercialPlan> = {
  venda: {
    id: "venda",
    name: "AlbionMKT Venda",
    amountCents: 3990,
    modules: ["sales_orders"],
    roleEnv: "DISCORD_ROLE_VENDA_ID",
  },
  compra: {
    id: "compra",
    name: "AlbionMKT Compra",
    amountCents: 4990,
    modules: ["purchase_orders"],
    roleEnv: "DISCORD_ROLE_COMPRA_ID",
  },
  completo: {
    id: "completo",
    name: "AlbionMKT Completo",
    amountCents: 9990,
    modules: ["purchase_orders", "sales_orders"],
    roleEnv: "DISCORD_ROLE_COMPLETO_ID",
  },
};

interface MercadoPagoPreference {
  id?: string;
  init_point?: string;
  sandbox_init_point?: string;
  message?: string;
}

interface MercadoPagoPayment {
  id?: number | string;
  status?: string;
  external_reference?: string;
  transaction_amount?: number;
  currency_id?: string;
}

function required(value: string | undefined, name: string): string {
  const resolved = value?.trim() ?? "";
  if (!resolved) throw new Error(`${name} nao configurado`);
  return resolved;
}

function bytesToBase64(value: Uint8Array): string {
  let binary = "";
  for (const byte of value) binary += String.fromCharCode(byte);
  return btoa(binary);
}

function base64ToBytes(value: string): Uint8Array<ArrayBuffer> {
  const binary = atob(value);
  const output = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) output[index] = binary.charCodeAt(index);
  return output;
}

async function encryptionKey(pepper: string): Promise<CryptoKey> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(pepper));
  return crypto.subtle.importKey("raw", digest, "AES-GCM", false, ["encrypt", "decrypt"]);
}

async function encryptLicenseKey(key: string, pepper: string): Promise<string> {
  const nonce = crypto.getRandomValues(new Uint8Array(12));
  const ciphertext = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv: nonce },
    await encryptionKey(pepper),
    new TextEncoder().encode(key),
  );
  return `${bytesToBase64(nonce)}.${bytesToBase64(new Uint8Array(ciphertext))}`;
}

async function decryptLicenseKey(secret: string, pepper: string): Promise<string> {
  const [nonceText, ciphertextText] = secret.split(".");
  if (!nonceText || !ciphertextText) throw new Error("segredo de entrega invalido");
  const plaintext = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: base64ToBytes(nonceText) },
    await encryptionKey(pepper),
    base64ToBytes(ciphertextText),
  );
  return new TextDecoder().decode(plaintext);
}

function planRoleId(env: Env, plan: CommercialPlan): string | undefined {
  return env[plan.roleEnv]?.trim() || undefined;
}

export function isCommercialPlanId(value: unknown): value is CommercialPlanId {
  return value === "compra" || value === "venda" || value === "completo";
}

export function formatPrice(amountCents: number): string {
  return `R$ ${(amountCents / 100).toFixed(2).replace(".", ",")}`;
}

export async function createCheckout(
  env: Env,
  discordUserId: string,
  guildId: string,
  planId: CommercialPlanId,
): Promise<{ orderId: string; checkoutUrl: string }> {
  const accessToken = required(env.MERCADOPAGO_ACCESS_TOKEN, "MERCADOPAGO_ACCESS_TOKEN");
  const baseUrl = required(env.PUBLIC_BASE_URL, "PUBLIC_BASE_URL").replace(/\/$/, "");
  const plan = COMMERCIAL_PLANS[planId];
  const orderId = crypto.randomUUID();
  const now = new Date().toISOString();
  await env.DB.prepare(
    `INSERT INTO commercial_orders
       (id, discord_user_id, guild_id, plan_id, amount_cents, status, created_at, updated_at)
     VALUES (?1, ?2, ?3, ?4, ?5, 'creating', ?6, ?6)`,
  ).bind(orderId, discordUserId, guildId, plan.id, plan.amountCents, now).run();

  const preferenceResponse = await fetch("https://api.mercadopago.com/checkout/preferences", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "application/json",
      "X-Idempotency-Key": orderId,
    },
    body: JSON.stringify({
      items: [{
        id: plan.id,
        title: `${plan.name} - acesso por 30 dias`,
        description: "Pagamento unico, sem renovacao automatica",
        quantity: 1,
        currency_id: "BRL",
        unit_price: plan.amountCents / 100,
      }],
      external_reference: orderId,
      notification_url: `${baseUrl}/webhooks/mercadopago?source_news=webhooks`,
      back_urls: {
        success: `${baseUrl}/pagamento/aprovado`,
        pending: `${baseUrl}/pagamento/pendente`,
        failure: `${baseUrl}/pagamento/falhou`,
      },
      auto_return: "approved",
      statement_descriptor: "ALBIONMKT",
      expires: true,
      expiration_date_to: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
    }),
  });
  const preference = await preferenceResponse.json<MercadoPagoPreference>();
  const checkoutUrl = preference.init_point ?? preference.sandbox_init_point;
  if (!preferenceResponse.ok || !preference.id || !checkoutUrl) {
    await env.DB.prepare(
      "UPDATE commercial_orders SET status = 'cancelled', updated_at = ?1, delivery_error = ?2 WHERE id = ?3",
    ).bind(new Date().toISOString(), `Mercado Pago HTTP ${preferenceResponse.status}`, orderId).run();
    throw new Error(preference.message || "nao foi possivel criar o pagamento");
  }
  await env.DB.prepare(
    "UPDATE commercial_orders SET status = 'pending', preference_id = ?1, updated_at = ?2 WHERE id = ?3",
  ).bind(preference.id, new Date().toISOString(), orderId).run();
  return { orderId, checkoutUrl };
}

function parseSignature(header: string): { timestamp: string; signature: string } | null {
  const entries = new Map(
    header.split(",").map((part) => {
      const separator = part.indexOf("=");
      return [part.slice(0, separator).trim(), part.slice(separator + 1).trim()];
    }),
  );
  const timestamp = entries.get("ts") ?? "";
  const signature = entries.get("v1") ?? "";
  return /^\d+$/.test(timestamp) && /^[a-f0-9]{64}$/i.test(signature)
    ? { timestamp, signature: signature.toLowerCase() }
    : null;
}

function toHex(value: ArrayBuffer): string {
  return [...new Uint8Array(value)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

function timingSafeEqual(left: string, right: string): boolean {
  let difference = left.length ^ right.length;
  const length = Math.max(left.length, right.length);
  for (let index = 0; index < length; index += 1) {
    difference |= (left.charCodeAt(index) || 0) ^ (right.charCodeAt(index) || 0);
  }
  return difference === 0;
}

export async function verifyMercadoPagoWebhook(
  env: Env,
  signatureHeader: string,
  requestId: string,
  dataId: string,
): Promise<boolean> {
  const parsed = parseSignature(signatureHeader);
  const secret = env.MERCADOPAGO_WEBHOOK_SECRET?.trim() ?? "";
  if (!parsed || !secret || !requestId || !dataId) return false;
  const manifest = `id:${dataId.toLowerCase()};request-id:${requestId};ts:${parsed.timestamp};`;
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const expected = toHex(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(manifest)));
  return timingSafeEqual(expected, parsed.signature);
}

async function discordRequest(env: Env, path: string, init: RequestInit): Promise<Response> {
  const token = required(env.DISCORD_BOT_TOKEN, "DISCORD_BOT_TOKEN");
  return fetch(`https://discord.com/api/v10${path}`, {
    ...init,
    headers: {
      Authorization: `Bot ${token}`,
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });
}

async function grantPlanRole(env: Env, order: CommercialOrderRow): Promise<void> {
  const plan = COMMERCIAL_PLANS[order.plan_id];
  const roleId = required(planRoleId(env, plan), plan.roleEnv);
  const added = await discordRequest(
    env,
    `/guilds/${order.guild_id}/members/${order.discord_user_id}/roles/${roleId}`,
    { method: "PUT" },
  );
  if (!added.ok) throw new Error(`Discord nao concedeu o cargo (HTTP ${added.status})`);
}

async function sendLicenseDm(env: Env, order: CommercialOrderRow, key: string): Promise<void> {
  const channelResponse = await discordRequest(env, "/users/@me/channels", {
    method: "POST",
    body: JSON.stringify({ recipient_id: order.discord_user_id }),
  });
  if (!channelResponse.ok) throw new Error(`Discord nao abriu a mensagem direta (HTTP ${channelResponse.status})`);
  const channel = await channelResponse.json<{ id?: string }>();
  if (!channel.id) throw new Error("Discord nao retornou o canal privado");
  const plan = COMMERCIAL_PLANS[order.plan_id];
  const download = env.ALBIONMKT_DOWNLOAD_URL?.trim();
  const message = [
    `Pagamento aprovado: **${plan.name}** por 30 dias.`,
    `Sua chave: \`${key}\``,
    `Validade: \`${order.access_expires_at}\``,
    download ? `Download oficial: ${download}` : "O download sera disponibilizado no canal oficial do servidor.",
    "Guarde esta mensagem. O pagamento e unico e nao possui renovacao automatica.",
  ].join("\n");
  const sent = await discordRequest(env, `/channels/${channel.id}/messages`, {
    method: "POST",
    body: JSON.stringify({ content: message, allowed_mentions: { parse: [] } }),
  });
  if (!sent.ok) throw new Error(`Discord nao entregou a mensagem (HTTP ${sent.status})`);
}

async function deliverOrder(env: Env, order: CommercialOrderRow, key: string): Promise<void> {
  try {
    await grantPlanRole(env, order);
    await sendLicenseDm(env, order, key);
    await env.DB.prepare(
      "UPDATE commercial_orders SET delivered_at = ?1, delivery_error = '', updated_at = ?1 WHERE id = ?2",
    ).bind(new Date().toISOString(), order.id).run();
  } catch (caught) {
    const message = caught instanceof Error ? caught.message : "falha desconhecida na entrega";
    await env.DB.prepare(
      "UPDATE commercial_orders SET delivery_error = ?1, updated_at = ?2 WHERE id = ?3",
    ).bind(message.slice(0, 500), new Date().toISOString(), order.id).run();
  }
}

export async function processMercadoPagoPayment(env: Env, paymentId: string): Promise<void> {
  const accessToken = required(env.MERCADOPAGO_ACCESS_TOKEN, "MERCADOPAGO_ACCESS_TOKEN");
  if (!/^\d+$/.test(paymentId)) throw new Error("ID de pagamento invalido");
  const paymentResponse = await fetch(`https://api.mercadopago.com/v1/payments/${paymentId}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!paymentResponse.ok) throw new Error(`Mercado Pago HTTP ${paymentResponse.status}`);
  const payment = await paymentResponse.json<MercadoPagoPayment>();
  const orderId = payment.external_reference ?? "";
  const order = await env.DB.prepare("SELECT * FROM commercial_orders WHERE id = ?1")
    .bind(orderId)
    .first<CommercialOrderRow>();
  if (!order) throw new Error("pedido nao encontrado");
  if (String(payment.id) !== paymentId) throw new Error("pagamento divergente");

  if (payment.status !== "approved") {
    const status = payment.status === "rejected" ? "rejected" : payment.status === "cancelled" ? "cancelled" : "pending";
    await env.DB.prepare(
      "UPDATE commercial_orders SET status = ?1, payment_id = ?2, updated_at = ?3 WHERE id = ?4 AND status <> 'approved'",
    ).bind(status, paymentId, new Date().toISOString(), order.id).run();
    return;
  }
  if (payment.currency_id !== "BRL" || Math.round(Number(payment.transaction_amount) * 100) !== order.amount_cents) {
    throw new Error("valor ou moeda do pagamento divergente");
  }
  if (order.status === "approved") {
    if (!order.delivered_at && order.license_secret) {
      await deliverOrder(env, order, await decryptLicenseKey(order.license_secret, env.ALBIONMKT_KEY_PEPPER));
    }
    return;
  }

  const claimed = await env.DB.prepare(
    `UPDATE commercial_orders SET status = 'processing', payment_id = ?1, updated_at = ?2
     WHERE id = ?3 AND status IN ('creating', 'pending', 'rejected', 'cancelled')`,
  ).bind(paymentId, new Date().toISOString(), order.id).run();
  if ((claimed.meta.changes ?? 0) !== 1) return;

  try {
    const plan = COMMERCIAL_PLANS[order.plan_id];
    const created = await createLicense(env, {
      discord_user_id: order.discord_user_id,
      duration_days: 30,
      duration_hours: null,
      device_limit: 1,
      modules: plan.modules,
      notes: `Pagamento Mercado Pago ${paymentId}; pedido ${order.id}`,
    });
    const key = String(created.key);
    const expiration = String(created.expires_at);
    const secret = await encryptLicenseKey(key, env.ALBIONMKT_KEY_PEPPER);
    await env.DB.prepare(
      `UPDATE commercial_orders
       SET status = 'approved', license_id = ?1, license_secret = ?2,
           access_expires_at = ?3, updated_at = ?4, delivery_error = ''
       WHERE id = ?5 AND status = 'processing'`,
    ).bind(String(created.id), secret, expiration, new Date().toISOString(), order.id).run();
    const approved = await env.DB.prepare("SELECT * FROM commercial_orders WHERE id = ?1")
      .bind(order.id)
      .first<CommercialOrderRow>();
    if (approved) await deliverOrder(env, approved, key);
  } catch (caught) {
    await env.DB.prepare(
      "UPDATE commercial_orders SET status = 'pending', updated_at = ?1, delivery_error = ?2 WHERE id = ?3 AND status = 'processing'",
    ).bind(
      new Date().toISOString(),
      (caught instanceof Error ? caught.message : "falha ao provisionar").slice(0, 500),
      order.id,
    ).run();
    throw caught;
  }
}

export async function latestUserAccess(
  env: Env,
  discordUserId: string,
): Promise<{ order: CommercialOrderRow; key: string } | null> {
  const order = await env.DB.prepare(
    `SELECT * FROM commercial_orders
     WHERE discord_user_id = ?1 AND status = 'approved'
     ORDER BY created_at DESC LIMIT 1`,
  ).bind(discordUserId).first<CommercialOrderRow>();
  if (!order?.license_secret) return null;
  return { order, key: await decryptLicenseKey(order.license_secret, env.ALBIONMKT_KEY_PEPPER) };
}

export async function removeExpiredRoles(env: Env): Promise<number> {
  if (!env.DISCORD_BOT_TOKEN) return 0;
  const now = new Date().toISOString();
  const expired = await env.DB.prepare(
    `SELECT * FROM commercial_orders
     WHERE status = 'approved' AND access_expires_at <= ?1 AND delivery_error <> 'cargo_expirado'`,
  ).bind(now).all<CommercialOrderRow>();
  let removed = 0;
  for (const order of expired.results) {
    const newer = await env.DB.prepare(
      `SELECT 1 AS active FROM commercial_orders
       WHERE discord_user_id = ?1 AND plan_id = ?2 AND status = 'approved' AND access_expires_at > ?3
       LIMIT 1`,
    ).bind(order.discord_user_id, order.plan_id, now).first<{ active: number }>();
    const roleId = planRoleId(env, COMMERCIAL_PLANS[order.plan_id]);
    if (!newer && roleId) {
      const response = await discordRequest(
        env,
        `/guilds/${order.guild_id}/members/${order.discord_user_id}/roles/${roleId}`,
        { method: "DELETE" },
      );
      if (!response.ok && response.status !== 404) continue;
      removed += 1;
    }
    await env.DB.prepare(
      "UPDATE commercial_orders SET delivery_error = 'cargo_expirado', updated_at = ?1 WHERE id = ?2",
    ).bind(now, order.id).run();
  }
  return removed;
}
