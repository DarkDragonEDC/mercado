import test from "node:test";
import assert from "node:assert/strict";
import {
  COMMERCIAL_PLANS,
  buildCommercialReference,
  parseCommercialReference,
  requireLicenseReservation,
  validateCommercialPayment
} from "../src/commercial-plans.js";
import { PaymentIdempotencyGuard } from "../src/payment-idempotency.js";
import { deliverPrivateMessage } from "../src/customer-delivery.js";

const guildId = "123456789012345678";
const discordUserId = "123456789012345678";
const purchaseId = "123e4567-e89b-12d3-a456-426614174000";

function payment(overrides = {}) {
  const plan = COMMERCIAL_PLANS[0];
  return {
    id: "987654321",
    status: "approved",
    transaction_amount: plan.price,
    currency_id: plan.currency,
    external_reference: buildCommercialReference({ guildId, discordUserId, planId: plan.id, purchaseId }),
    metadata: {
      discord_user_id: discordUserId,
      guild_id: guildId,
      plan: plan.id,
      purchase_id: purchaseId
    },
    ...overrides
  };
}

test("mantém planos oficiais na ordem e nos preços definidos", () => {
  assert.deepEqual(COMMERCIAL_PLANS.map(({ id, price }) => [id, price]), [
    ["sales", 39.90],
    ["purchase", 49.90],
    ["complete", 99.90]
  ]);
});

test("external_reference identifica usuário, servidor, plano e compra", () => {
  const reference = buildCommercialReference({ guildId, discordUserId, planId: "purchase", purchaseId });
  assert.deepEqual(parseCommercialReference(reference), {
    guildId,
    discordUserId,
    planId: "purchase",
    purchaseId,
    legacy: false
  });
});

test("checkout leva identificação completa na referência e metadata", async () => {
  process.env.DISCORD_GUILD_ID = guildId;
  process.env.PUBLIC_BASE_URL = "https://bot.example.test";
  const { buildPaymentPreferencePayload } = await import("../src/mercadopago.js");
  for (const plan of COMMERCIAL_PLANS) {
    const payload = buildPaymentPreferencePayload({
      discordUserId,
      email: "cliente@example.test",
      planId: plan.id,
      purchaseId
    });
    assert.equal(payload.items[0].unit_price, plan.price);
    assert.equal(payload.items[0].currency_id, "BRL");
    assert.equal(payload.metadata.discord_user_id, discordUserId);
    assert.equal(payload.metadata.guild_id, guildId);
    assert.equal(payload.metadata.plan, plan.id);
    assert.equal(payload.metadata.purchase_id, purchaseId);
    assert.match(payload.external_reference, /^albionmkt:v1:/);
  }
});

test("aprova somente pagamento com status, valor, moeda e metadata exatos", () => {
  assert.equal(validateCommercialPayment(payment(), guildId).ok, true);
  for (const altered of [
    { status: "pending" },
    { status: "rejected" },
    { transaction_amount: 39.89 },
    { currency_id: "USD" },
    { metadata: { ...payment().metadata, plan: "purchase" } },
    { metadata: { ...payment().metadata, discord_user_id: "999999999999999999" } }
  ]) {
    assert.equal(validateCommercialPayment(payment(altered), guildId).ok, false);
  }
});

test("webhook duplicado executa a entrega apenas uma vez", async () => {
  const guard = new PaymentIdempotencyGuard();
  let executions = 0;
  const processed = new Set();
  const operation = () => guard.run("987654321", async (id) => processed.has(id), async () => {
    executions += 1;
    await new Promise((resolve) => setTimeout(resolve, 10));
    processed.add("987654321");
    return true;
  });
  const [first, duplicate] = await Promise.all([operation(), operation()]);
  assert.equal(executions, 1);
  assert.equal([first.duplicate, duplicate.duplicate].filter(Boolean).length, 1);
});

test("mensagem privada bloqueada é registrada sem expor conteúdo", async () => {
  const client = { users: { fetch: async () => ({ send: async () => { throw new Error("DM bloqueada"); } }) } };
  const result = await deliverPrivateMessage(client, discordUserId, "mensagem privada", true);
  assert.equal(result.dmDelivered, false);
  assert.equal(result.downloadPrepared, true);
  assert.match(result.errorMessage, /DM bloqueada/);
});

test("falta de key interrompe a liberação", () => {
  assert.throws(() => requireLicenseReservation(null), /Nenhuma key/);
  assert.equal(requireLicenseReservation({ licenseKey: "TESTE" }).licenseKey, "TESTE");
});
