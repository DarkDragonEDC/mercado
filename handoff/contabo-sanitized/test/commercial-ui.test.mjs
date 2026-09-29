import test from "node:test";
import assert from "node:assert/strict";

process.env.DISCORD_GUILD_ID ||= "123456789012345678";
const { commercialButtons, commercialPaymentModal, onboardingStep } = await import("../src/interaction-ui.js");

test("botões persistentes aparecem na ordem oficial", () => {
  const buttons = commercialButtons()[0].components.map((button) => button.data);
  assert.deepEqual(buttons.slice(0, 3).map((button) => button.custom_id), [
    "commercial:sales",
    "commercial:purchase",
    "commercial:complete"
  ]);
  assert.deepEqual(buttons.slice(0, 3).map((button) => button.label), [
    "Venda — R$ 39,90",
    "Compra — R$ 49,90",
    "MKT Completo"
  ]);
});

test("cada botão abre formulário vinculado ao plano correto", () => {
  for (const planId of ["sales", "purchase", "complete"]) {
    assert.equal(commercialPaymentModal(planId).data.custom_id, `commercial:checkout:${planId}`);
  }
});

test("introdução apresenta os três planos sem preço antigo", () => {
  const content = JSON.stringify(onboardingStep("plan").embeds[0].toJSON());
  assert.match(content, /39,90/);
  assert.match(content, /49,90/);
  assert.match(content, /99,90/);
  assert.doesNotMatch(content, /29,90/);
});
