import {
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  EmbedBuilder,
  ModalBuilder,
  TextInputBuilder,
  TextInputStyle
} from "discord.js";
import { config } from "./config.js";
import { COMMERCIAL_PLANS, formatPlanPrice, requireCommercialPlan } from "./commercial-plans.js";

export const UI_IDS = Object.freeze({
  onboardingStart: "onboarding:start",
  onboardingFeatures: "onboarding:features",
  onboardingPlan: "onboarding:plan",
  onboardingTerms: "onboarding:terms",
  onboardingAccept: "onboarding:accept",
  onboardingHelp: "onboarding:help",
  freeTrial: "sales:free-trial",
  salesOpen: "sales:open",
  salesModal: "sales:modal",
  salesEmail: "sales:email",
  pixOpen: "sales:pix-open",
  pixModal: "sales:pix-modal",
  subscriptionStatus: "subscription:status",
  commercialPurchase: "commercial:purchase",
  commercialSales: "commercial:sales",
  commercialComplete: "commercial:complete",
  commercialEmail: "commercial:email",
  supportOpen: "support:open",
  supportModal: "support:modal",
  supportSubject: "support:subject"
});

export const BRAND = Object.freeze({
  navy: 0x0b2239,
  copper: 0xc98245,
  cream: 0xf6e4be,
  success: 0x3ba55d,
  error: 0xed4245
});

function navigationRow({ back, next, accept = false }) {
  const row = new ActionRowBuilder();
  if (back) {
    row.addComponents(new ButtonBuilder()
      .setCustomId(back)
      .setLabel("Voltar")
      .setEmoji("⬅️")
      .setStyle(ButtonStyle.Secondary));
  }
  if (next) {
    row.addComponents(new ButtonBuilder()
      .setCustomId(next)
      .setLabel("Continuar")
      .setEmoji("➡️")
      .setStyle(ButtonStyle.Primary));
  }
  if (accept) {
    row.addComponents(new ButtonBuilder()
      .setCustomId(UI_IDS.onboardingAccept)
      .setLabel("Concordar e acessar")
      .setEmoji("✅")
      .setStyle(ButtonStyle.Success));
  }
  return row;
}

export function onboardingStep(step) {
  if (step === "features") {
    return {
      embeds: [new EmbedBuilder()
        .setColor(BRAND.navy)
        .setTitle("Etapa 2 de 4 — Recursos do programa")
        .setDescription([
          "O AlbionMKT foi criado para tornar decisões de mercado mais rápidas e organizadas.",
          "",
          "**Você encontrará:**",
          "• ferramentas de leitura e comparação de preços;",
          "• apoio para análise de margem e oportunidades;",
          "• recursos de mapa, rotas e organização;",
          "• atualizações, guias e suporte em um único lugar."
        ].join("\n"))
        .setFooter({ text: "AlbionMKT • Introdução 2/4" })],
      components: [navigationRow({ back: UI_IDS.onboardingStart, next: UI_IDS.onboardingPlan })]
    };
  }

  if (step === "plan") {
    return {
      embeds: [new EmbedBuilder()
        .setColor(BRAND.copper)
        .setTitle("Etapa 3 de 4 — Planos e acesso")
        .addFields(
          { name: "Teste gratis", value: `${config.freeTrialDays} dia, uma unica vez por usuario`, inline: true },
          ...COMMERCIAL_PLANS.map((plan) => ({
            name: `${plan.name} — ${formatPlanPrice(plan)}`,
            value: `${plan.description}\nAcesso por ${plan.days} dias.`
          })),
          { name: "Entrega", value: "Após a aprovação do pagamento, cargo, key e download são enviados automaticamente por mensagem privada." },
          { name: "Suporte", value: "O atendimento ocorre em um ticket privado dentro do servidor." }
        )
        .setFooter({ text: "AlbionMKT • Introdução 3/4" })],
      components: [navigationRow({ back: UI_IDS.onboardingFeatures, next: UI_IDS.onboardingTerms })]
    };
  }

  if (step === "terms") {
    return {
      embeds: [new EmbedBuilder()
        .setColor(BRAND.copper)
        .setTitle("Etapa 4 de 4 — Confirmação")
        .setDescription([
          "Ao continuar, você confirma que leu e concorda com estas condições:",
          "",
          "• a key e os links de download são pessoais;",
          "• não é permitido compartilhar, revender ou publicar o acesso;",
          "• dados de pagamento, senhas e tokens nunca devem ser enviados em canais públicos;",
          "• o acesso exclusivo depende de uma assinatura ativa;",
          "• o uso deve respeitar as regras do servidor e do jogo."
        ].join("\n"))
        .setFooter({ text: "AlbionMKT • Termos de entrada v1 • Introdução 4/4" })],
      components: [navigationRow({ back: UI_IDS.onboardingPlan, accept: true })]
    };
  }

  return {
    embeds: [new EmbedBuilder()
      .setColor(BRAND.navy)
      .setTitle("Etapa 1 de 4 — Conheça o AlbionMKT")
      .setDescription([
        "O **AlbionMKT** é uma ferramenta de apoio para jogadores que desejam analisar o mercado com mais clareza, agilidade e organização.",
        "",
        "Esta introdução apresenta os recursos, o plano de acesso e as condições essenciais. Leva menos de um minuto e será exibida somente para você."
      ].join("\n"))
      .setFooter({ text: "AlbionMKT • Introdução 1/4" })],
    components: [navigationRow({ next: UI_IDS.onboardingFeatures })]
  };
}

export function entryButtons() {
  return [new ActionRowBuilder().addComponents(
    new ButtonBuilder()
      .setCustomId(UI_IDS.onboardingStart)
      .setLabel("Conhecer o AlbionMKT")
      .setEmoji("⛵")
      .setStyle(ButtonStyle.Primary),
    new ButtonBuilder()
      .setCustomId(UI_IDS.onboardingPlan)
      .setLabel("Plano e acesso")
      .setEmoji("💳")
      .setStyle(ButtonStyle.Secondary),
    new ButtonBuilder()
      .setCustomId(UI_IDS.onboardingHelp)
      .setLabel("Preciso de ajuda")
      .setEmoji("🛟")
      .setStyle(ButtonStyle.Secondary)
  )];
}

export function salesButtons() {
  return commercialButtons();
}

export function supportButtons() {
  return [new ActionRowBuilder().addComponents(
    new ButtonBuilder()
      .setCustomId(UI_IDS.supportOpen)
      .setLabel("Abrir atendimento privado")
      .setEmoji("🎫")
      .setStyle(ButtonStyle.Primary)
  )];
}

export function commercialButtons() {
  return [new ActionRowBuilder().addComponents(
    new ButtonBuilder()
      .setCustomId(UI_IDS.commercialSales)
      .setLabel("Venda — R$ 39,90")
      .setEmoji("💰")
      .setStyle(ButtonStyle.Primary),
    new ButtonBuilder()
      .setCustomId(UI_IDS.commercialPurchase)
      .setLabel("Compra — R$ 49,90")
      .setEmoji("🛒")
      .setStyle(ButtonStyle.Primary),
    new ButtonBuilder()
      .setCustomId(UI_IDS.commercialComplete)
      .setLabel("MKT Completo")
      .setEmoji("⭐")
      .setStyle(ButtonStyle.Success),
    new ButtonBuilder()
      .setCustomId(UI_IDS.subscriptionStatus)
      .setLabel("Minha assinatura")
      .setEmoji("🔎")
      .setStyle(ButtonStyle.Secondary),
    new ButtonBuilder()
      .setCustomId(UI_IDS.supportOpen)
      .setLabel("Falar com a equipe")
      .setEmoji("🎫")
      .setStyle(ButtonStyle.Secondary)
  )];
}

export function commercialPlanReply(kind) {
  const plan = requireCommercialPlan(kind);

  return {
    embeds: [new EmbedBuilder()
      .setColor(BRAND.copper)
      .setTitle(plan.name)
      .setDescription(plan.description)
      .addFields(
        { name: "Valor", value: `${formatPlanPrice(plan)} por ${plan.days} dias`, inline: true },
        { name: "Entrega", value: "Após a aprovação, key, cargo e download são enviados por mensagem privada." }
      )
      .setFooter({ text: "AlbionMKT • atendimento comercial" })],
    components: []
  };
}

export function commercialPaymentModal(planId) {
  const plan = requireCommercialPlan(planId);
  return new ModalBuilder()
    .setCustomId(`commercial:checkout:${plan.id}`)
    .setTitle(`${plan.name} — ${formatPlanPrice(plan)}`.slice(0, 45))
    .addComponents(new ActionRowBuilder().addComponents(
      new TextInputBuilder()
        .setCustomId(UI_IDS.commercialEmail)
        .setLabel("E-mail utilizado no Mercado Pago")
        .setPlaceholder("seuemail@exemplo.com")
        .setStyle(TextInputStyle.Short)
        .setRequired(true)
        .setMaxLength(254)
    ));
}

export function salesModal() {
  return new ModalBuilder()
    .setCustomId(UI_IDS.salesModal)
    .setTitle("Assinar o AlbionMKT")
    .addComponents(new ActionRowBuilder().addComponents(
      new TextInputBuilder()
        .setCustomId(UI_IDS.salesEmail)
        .setLabel("E-mail utilizado no Mercado Pago")
        .setPlaceholder("seuemail@exemplo.com")
        .setStyle(TextInputStyle.Short)
        .setRequired(true)
        .setMaxLength(254)
    ));
}

export function pixPaymentModal() {
  return new ModalBuilder()
    .setCustomId(UI_IDS.pixModal)
    .setTitle("Pagar 30 dias via Pix")
    .addComponents(new ActionRowBuilder().addComponents(
      new TextInputBuilder()
        .setCustomId(UI_IDS.salesEmail)
        .setLabel("E-mail utilizado no Mercado Pago")
        .setPlaceholder("seuemail@exemplo.com")
        .setStyle(TextInputStyle.Short)
        .setRequired(true)
        .setMaxLength(254)
    ));
}

export function supportModal() {
  return new ModalBuilder()
    .setCustomId(UI_IDS.supportModal)
    .setTitle("Suporte AlbionMKT")
    .addComponents(new ActionRowBuilder().addComponents(
      new TextInputBuilder()
        .setCustomId(UI_IDS.supportSubject)
        .setLabel("Como podemos ajudar?")
        .setPlaceholder("Descreva brevemente o assunto")
        .setStyle(TextInputStyle.Paragraph)
        .setRequired(true)
        .setMinLength(10)
        .setMaxLength(500)
    ));
}
