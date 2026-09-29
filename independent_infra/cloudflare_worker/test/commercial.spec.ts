import { env } from "cloudflare:workers";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  COMMERCIAL_PLANS,
  createCheckout,
  processMercadoPagoPayment,
  verifyMercadoPagoWebhook,
} from "../src/commercial";
import type { CommercialOrderRow, Env } from "../src/types";

const GUILD_ID = "1541428118533967972";
const USER_ID = "1366066241667862680";
const WEBHOOK_SECRET = "webhook-secret-for-tests";

function testEnv(): Env {
  return {
    ...(env as unknown as Env),
    MERCADOPAGO_ACCESS_TOKEN: "APP_USR-test-token",
    MERCADOPAGO_WEBHOOK_SECRET: WEBHOOK_SECRET,
    PUBLIC_BASE_URL: "https://albionmkt.test",
    DISCORD_BOT_TOKEN: "discord-test-token",
    DISCORD_ROLE_COMPRA_ID: "1001",
    DISCORD_ROLE_VENDA_ID: "1002",
    DISCORD_ROLE_COMPLETO_ID: "1003",
    ALBIONMKT_DOWNLOAD_URL: "https://download.test/albionmkt.exe",
  };
}

async function signature(dataId: string, requestId: string, timestamp: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(WEBHOOK_SECRET),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const manifest = `id:${dataId};request-id:${requestId};ts:${timestamp};`;
  const digest = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(manifest));
  const hex = [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
  return `ts=${timestamp},v1=${hex}`;
}

describe("vendas independentes", () => {
  beforeEach(async () => {
    vi.restoreAllMocks();
    const database = (env as Cloudflare.Env).DB;
    await database.batch([
      database.prepare("DELETE FROM commercial_orders"),
      database.prepare("DELETE FROM license_devices"),
      database.prepare("DELETE FROM licenses"),
    ]);
  });

  it("cria checkout com preço fixo, referência interna e sem recorrência", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => {
      const payload = JSON.parse(String(init?.body));
      expect(payload.items[0].unit_price).toBe(99.9);
      expect(payload.items[0].title).toContain("30 dias");
      expect(payload).not.toHaveProperty("auto_recurring");
      expect(payload.external_reference).toMatch(/^[a-f0-9-]{36}$/);
      expect(new Headers(init?.headers).get("X-Idempotency-Key")).toBe(payload.external_reference);
      return Response.json({ id: "preference-1", init_point: "https://mercadopago.test/pay" });
    });

    const created = await createCheckout(testEnv(), USER_ID, GUILD_ID, "completo");
    expect(created.checkoutUrl).toBe("https://mercadopago.test/pay");
    const order = await testEnv().DB.prepare("SELECT * FROM commercial_orders WHERE id = ?1")
      .bind(created.orderId).first<CommercialOrderRow>();
    expect(order?.status).toBe("pending");
    expect(order?.amount_cents).toBe(COMMERCIAL_PLANS.completo.amountCents);
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("valida a assinatura HMAC do webhook", async () => {
    const dataId = "123456789";
    const requestId = "request-abc";
    const timestamp = "1704908010";
    const validSignature = await signature(dataId, requestId, timestamp);
    expect(await verifyMercadoPagoWebhook(testEnv(), validSignature, requestId, dataId)).toBe(true);
    expect(await verifyMercadoPagoWebhook(testEnv(), validSignature, requestId, "987654321")).toBe(false);
  });

  it("aprova, entrega e não duplica a licença ao repetir a notificação", async () => {
    const orderId = crypto.randomUUID();
    const now = new Date().toISOString();
    const currentEnv = testEnv();
    await currentEnv.DB.prepare(
      `INSERT INTO commercial_orders
       (id, discord_user_id, guild_id, plan_id, amount_cents, status, created_at, updated_at)
       VALUES (?1, ?2, ?3, 'compra', 4990, 'pending', ?4, ?4)`,
    ).bind(orderId, USER_ID, GUILD_ID, now).run();

    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.includes("api.mercadopago.com/v1/payments/777")) {
        return Response.json({
          id: 777,
          status: "approved",
          external_reference: orderId,
          transaction_amount: 49.9,
          currency_id: "BRL",
        });
      }
      if (url.endsWith("/users/@me/channels")) return Response.json({ id: "dm-channel" });
      if (url.endsWith("/channels/dm-channel/messages")) return Response.json({ id: "message-1" });
      if (init?.method === "PUT" || init?.method === "DELETE") return new Response(null, { status: 204 });
      throw new Error(`fetch inesperado: ${url}`);
    });

    await processMercadoPagoPayment(currentEnv, "777");
    await processMercadoPagoPayment(currentEnv, "777");

    const order = await currentEnv.DB.prepare("SELECT * FROM commercial_orders WHERE id = ?1")
      .bind(orderId).first<CommercialOrderRow>();
    const licenses = await currentEnv.DB.prepare("SELECT COUNT(*) AS total FROM licenses")
      .first<{ total: number }>();
    expect(order?.status).toBe("approved");
    expect(order?.delivered_at).toBeTruthy();
    expect(order?.license_secret).not.toContain("ALBIONMKT-");
    expect(licenses?.total).toBe(1);
  });
});
