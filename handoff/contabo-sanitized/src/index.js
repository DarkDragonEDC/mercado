import express from "express";
import crypto from "node:crypto";
import {
  ActivityType,
  ChannelType,
  Client,
  EmbedBuilder,
  GatewayIntentBits,
  PermissionFlagsBits,
  ThreadAutoArchiveDuration
} from "discord.js";
import { config, validateConfig } from "./config.js";
import { grantRole, grantVisitorRole, revokeRole } from "./discord-access.js";
import {
  createPaymentPreference,
  createSubscription,
  getAuthorizedPayment,
  getAuthorizedPaymentsByPayment,
  getAuthorizedPaymentsBySubscription,
  getPayment,
  getRecentPayments,
  getSubscription,
  parseDiscordReference,
  verifyWebhook
} from "./mercadopago.js";
import {
  findByPaymentId,
  findByPurchaseId,
  findByDiscordUser,
  findByPreapprovalId,
  findPendingStaticTests,
  listSubscriptions,
  saveSubscription
} from "./store.js";
import { publishPanels } from "./panels.js";
import {
  createSalesCsvAttachment,
  publishSalesTable,
  registerSale
} from "./sales-ledger.js";
import { claimFreeTrial, reserveLicenseKey } from "./license-key-pool.js";
import {
  createLicense,
  formatLicenseModules,
  getLicense,
  getLicenseStats,
  listLicenses,
  migrateLegacyLicenses,
  modulesForAccess,
  updateLicense,
  validateLicense
} from "./license-store.js";
import { saveOnboardingAcceptance } from "./onboarding-store.js";
import {
  BRAND,
  UI_IDS,
  commercialPaymentModal,
  onboardingStep,
  pixPaymentModal,
  salesModal,
  supportModal
} from "./interaction-ui.js";
import { SERVER_IDS } from "./server-layout.js";
import { processRenewalReminders } from "./renewal-reminders.js";
import { publishLicenseMonitor } from "./license-monitor.js";
import {
  createPurchaseId,
  formatPlanPrice,
  requireLicenseReservation,
  requireCommercialPlan,
  validateCommercialPayment
} from "./commercial-plans.js";
import { PaymentIdempotencyGuard } from "./payment-idempotency.js";
import { deliverPrivateMessage } from "./customer-delivery.js";

validateConfig();

const client = new Client({ intents: [GatewayIntentBits.Guilds] });
const app = express();
app.use(express.json());

const BRAND_COLOR = 0xd4af37;
const SUCCESS_COLOR = 0x2ecc71;
const ERROR_COLOR = 0xe74c3c;
const licenseApiAttempts = new Map();
const processingAuthorizedInvoices = new Set();
const commercialPaymentGuard = new PaymentIdempotencyGuard();

function allowLicenseApiRequest(ip) {
  const now = Date.now();
  const current = licenseApiAttempts.get(ip) || { start: now, count: 0 };
  if (now - current.start >= 60_000) {
    current.start = now;
    current.count = 0;
  }
  current.count += 1;
  licenseApiAttempts.set(ip, current);
  return current.count <= 60;
}

function formatLicenseDate(value) {
  const date = new Date(value || 0);
  if (Number.isNaN(date.getTime()) || !value) return "Não informada";
  return new Intl.DateTimeFormat("pt-BR", {
    timeZone: "America/Sao_Paulo",
    dateStyle: "short",
    timeStyle: "short"
  }).format(date);
}

function licenseSummary(record) {
  return [
    `ID: \`${record.id}\``,
    `Key: \`${record.keyPrefix}\``,
    `Cliente: ${record.discordUserId ? `<@${record.discordUserId}>` : "nao informado"}`,
    `Status: **${record.effectiveStatus}**`,
    `Vencimento: **${formatLicenseDate(record.expiresAt)}**`,
    `Computadores: **${record.devices.length}/${record.maxDevices}**`,
    `Acesso: **${formatLicenseModules(record.modules)}**`,
    `Modulos: **${(record.modules || ["purchase_orders"]).join(", ")}**`
  ].join("\n");
}

async function sendOperationalLog(title, fields = [], color = BRAND_COLOR) {
  if (!config.logChannelId || !client.isReady()) return;
  try {
    const channel = await client.channels.fetch(config.logChannelId);
    if (!channel?.isTextBased()) return;
    const embed = new EmbedBuilder()
      .setColor(color)
      .setTitle(title)
      .addFields(fields.map((field) => ({
        name: field.name,
        value: String(field.value || "-").slice(0, 1024),
        inline: Boolean(field.inline)
      })))
      .setFooter({ text: "AlbionMKT • registro automático" })
      .setTimestamp();
    await channel.send({ embeds: [embed] });
  } catch (error) {
    console.error("Falha ao enviar log ao Discord:", error);
  }
}

async function recordSaleSafely(record) {
  try {
    return await registerSale(client, record);
  } catch (error) {
    console.error("Falha ao atualizar o controle de vendas:", error);
    return null;
  }
}

async function publishLicenseMonitorSafely() {
  try {
    return await publishLicenseMonitor(client);
  } catch (error) {
    console.error("Falha ao atualizar o painel de licencas:", error);
    return null;
  }
}

async function reserveKeySafely({ sourceId, discordUserId, username = "", paymentId, plan = null }) {
  try {
    const reservation = await reserveLicenseKey({
      sourceId,
      discordUserId,
      username,
      paymentId,
      planId: plan?.id || "",
      planName: plan?.name || "",
      modules: plan?.modules,
      days: plan?.days
    });
    await sendOperationalLog("Key reservada para entrega", [
      { name: "Usuário", value: `<@${discordUserId}>`, inline: true },
      { name: "Pagamento", value: String(paymentId || sourceId), inline: true },
      { name: "Key", value: `Final ${reservation.licenseKey.slice(-5)}`, inline: true }
    ], SUCCESS_COLOR);
    await publishLicenseMonitorSafely();
    return reservation;
  } catch (error) {
    console.error("Falha ao reservar key:", error);
    await sendOperationalLog("Falha na reserva de key", [
      { name: "Usuário", value: `<@${discordUserId}>`, inline: true },
      { name: "Pagamento", value: String(paymentId || sourceId), inline: true },
      { name: "Erro", value: error.message }
    ], ERROR_COLOR);
    return null;
  }
}

async function seedSalesLedger() {
  if (!config.salesControlChannelId) return;
  const subscriptions = await listSubscriptions();
  for (const item of subscriptions.filter((record) => record.active)) {
    await recordSaleSafely({
      sourceId: item.paymentId ? `payment:${item.paymentId}` : item.preapprovalId,
      paymentId: item.paymentId || "",
      discordUserId: item.discordUserId,
      kind: item.kind,
      planName: item.planName || (item.kind === "free_trial"
        ? config.freeTrialName
        : item.kind === "static_test" ? "Teste AlbionMKT" : config.planName),
      amount: Number(item.amount ?? (item.kind === "free_trial" ? 0 : item.kind === "static_test" ? config.testPaymentAmount : config.planPrice)),
      currency: item.currency || config.currency,
      status: item.status,
      paidAt: item.createdAt || item.updatedAt,
      expiresAt: item.expiresAt
    });
  }
  await publishSalesTable(client).catch((error) =>
    console.error("Falha ao publicar a tabela de vendas:", error)
  );
}

function ticketName(user) {
  const safe = user.username.toLowerCase().replace(/[^a-z0-9-]/g, "-").replace(/-+/g, "-").slice(0, 40);
  return `suporte-${safe || user.id.slice(-6)}`;
}

async function openSupportTicket(interaction, subject, parentChannelId = config.supportChannelId) {
  if (!parentChannelId) {
    await interaction.reply({ content: "O canal de suporte ainda não foi configurado.", ephemeral: true });
    return;
  }
  const supportChannel = await client.channels.fetch(parentChannelId);
  if (!supportChannel?.isTextBased() || !supportChannel.threads) {
    await interaction.reply({ content: "O canal de suporte está indisponível no momento.", ephemeral: true });
    return;
  }

  const active = await supportChannel.threads.fetchActive();
  const existing = active.threads.find((thread) =>
    thread.name.endsWith(`-${interaction.user.id.slice(-6)}`) ||
    thread.name === ticketName(interaction.user)
  );
  if (existing) {
    await interaction.reply({ content: `Você já possui um atendimento aberto: <#${existing.id}>.`, ephemeral: true });
    return;
  }

  await interaction.deferReply({ ephemeral: true });
  const ticketSubject = subject || interaction.options?.getString?.("assunto", true) || "Atendimento solicitado";
  const thread = await supportChannel.threads.create({
    name: `${ticketName(interaction.user)}-${interaction.user.id.slice(-6)}`.slice(0, 100),
    autoArchiveDuration: ThreadAutoArchiveDuration.OneDay,
    type: ChannelType.PrivateThread,
    invitable: false,
    reason: `Atendimento solicitado por ${interaction.user.tag}`
  });
  await thread.members.add(interaction.user.id);
  await thread.send({
    content: `<@${interaction.user.id}>`,
    embeds: [
      new EmbedBuilder()
        .setColor(BRAND_COLOR)
        .setTitle("Atendimento AlbionMKT")
        .setDescription("Seu atendimento e privado. Descreva os detalhes e aguarde a equipe responder.")
        .addFields(
          { name: "Assunto", value: ticketSubject.slice(0, 1024) },
          { name: "Como encerrar", value: "Use `/fechar-suporte` dentro deste atendimento." }
        )
        .setTimestamp()
    ]
  });
  await sendOperationalLog("Ticket de suporte aberto", [
    { name: "Usuário", value: `<@${interaction.user.id}>`, inline: true },
    { name: "Ticket", value: `<#${thread.id}>`, inline: true },
    { name: "Assunto", value: ticketSubject.slice(0, 1024) }
  ]);
  await interaction.editReply(`Atendimento criado com sucesso: <#${thread.id}>.`);
}

async function closeSupportTicket(interaction) {
  const validParents = new Set([config.supportChannelId, config.entryChannelId].filter(Boolean));
  if (!interaction.channel?.isThread() || !validParents.has(interaction.channel.parentId)) {
    await interaction.reply({ content: "Use este comando dentro de um atendimento privado.", ephemeral: true });
    return;
  }
  await interaction.reply("Atendimento encerrado. Este tópico será arquivado.");
  await sendOperationalLog("Ticket de suporte encerrado", [
    { name: "Usuário", value: `<@${interaction.user.id}>`, inline: true },
    { name: "Ticket", value: interaction.channel.name, inline: true }
  ]);
  await interaction.channel.setLocked(true, `Encerrado por ${interaction.user.tag}`);
  await interaction.channel.setArchived(true, `Encerrado por ${interaction.user.tag}`);
}

function createDownloadLink(discordUserId) {
  if (!config.downloadFilePath || !config.downloadSecret) return "";
  const expires = Math.floor(Date.now() / 1000) + config.downloadLinkDays * 86_400;
  const payload = `${discordUserId}:${expires}`;
  const signature = crypto.createHmac("sha256", config.downloadSecret).update(payload).digest("hex");
  const query = new URLSearchParams({ user: discordUserId, expires: String(expires), signature });
  return `${config.publicBaseUrl}/download/albionmkt?${query}`;
}

function correctedAccessApprovedMessage(discordUserId, licenseKey, plan = null, expiresAt = "") {
  const downloadLink = createDownloadLink(discordUserId);
  const expiration = expiresAt ? formatLicenseDate(expiresAt) : "30 dias após a aprovação";
  return [
    "## \u2705 Pagamento aprovado!",
    "Sua compra do **AlbionMKT** foi confirmada.",
    "",
    `**Plano:** ${plan?.name || config.planName}`,
    `**Validade:** ${expiration}`,
    "**Key de acesso:**",
    licenseKey ? `\`${licenseKey}\`` : "A key esta sendo preparada pela equipe. Use `/suporte` se necessario.",
    licenseKey ? "Esta key é pessoal. Não compartilhe com outras pessoas." : "",
    "",
    "**Baixe o programa diretamente por esta mensagem:**",
    downloadLink || "O arquivo est\u00e1 sendo preparado. Entre em contato com o suporte.",
    downloadLink ? `Este link \u00e9 pessoal e v\u00e1lido por ${config.downloadLinkDays} dias. N\u00e3o o compartilhe.` : "",
    "",
    "**Como prosseguir:**",
    "1. Baixe o programa pelo link acima.",
    "2. Execute o instalador do AlbionMKT.",
    "3. Informe sua key na tela de ativação.",
    "4. Consulte os guias do servidor.",
    "5. Use o suporte privado se precisar de ajuda.",
    "",
    config.supportChannelId
      ? `Se precisar de ajuda, utilize <#${config.supportChannelId}>.`
      : "Se precisar de ajuda, utilize `/suporte`.",
    "Voc\u00ea tamb\u00e9m pode consultar seu acesso com `/minha-assinatura`."
  ].filter(Boolean).join("\n");
}

async function notifyAccessApproved(discordUserId, fallbackChannelId, licenseKey, plan = null, expiresAt = "") {
  const downloadPrepared = Boolean(createDownloadLink(discordUserId));
  const delivery = await deliverPrivateMessage(
    client,
    discordUserId,
    correctedAccessApprovedMessage(discordUserId, licenseKey, plan, expiresAt),
    downloadPrepared
  );
  if (delivery.dmDelivered) {
    console.log(`Confirmação de compra enviada por DM a ${discordUserId}.`);
    return delivery;
  }
  console.warn(`Não foi possível enviar DM a ${discordUserId}: ${delivery.errorMessage}`);

  if (!fallbackChannelId) return delivery;
  try {
    const channel = await client.channels.fetch(fallbackChannelId);
    if (channel?.isTextBased()) {
      await channel.send({
        content: `<@${discordUserId}> seu pagamento foi aprovado, mas não foi possível enviar a key por mensagem privada. Ative as mensagens diretas e use \`/suporte\`. Sua key não será publicada neste canal.`
      });
      console.log(`ConfirmaÃ§Ã£o de compra enviada no canal ${fallbackChannelId}.`);
    }
  } catch (error) {
    console.error(`Falha ao enviar confirmaÃ§Ã£o no canal ${fallbackChannelId}:`, error);
  }
  return delivery;
}

function freeTrialApprovedMessage(discordUserId, licenseKey, expiresAt) {
  const downloadLink = createDownloadLink(discordUserId);
  const expiration = new Intl.DateTimeFormat("pt-BR", {
    timeZone: "America/Sao_Paulo",
    dateStyle: "short",
    timeStyle: "short"
  }).format(new Date(expiresAt));
  return [
    "## 🎁 Teste gratis liberado!",
    `Seu acesso de **${config.freeTrialDays} dia** ao AlbionMKT foi ativado.`,
    `Valido ate: **${expiration}**`,
    "",
    "**Sua key de acesso:**",
    `\`${licenseKey}\``,
    "Esta key e pessoal e o teste gratis pode ser utilizado somente uma vez por usuario do Discord.",
    "",
    "**Baixe o programa:**",
    downloadLink || "O arquivo esta sendo preparado. Use `/suporte` se necessario.",
    downloadLink ? `O link e pessoal e valido por ${config.downloadLinkDays} dias.` : ""
  ].filter(Boolean).join("\n");
}

async function notifyFreeTrialApproved(discordUserId, fallbackChannelId, licenseKey, expiresAt) {
  try {
    const user = await client.users.fetch(discordUserId);
    await user.send(freeTrialApprovedMessage(discordUserId, licenseKey, expiresAt));
    return true;
  } catch (error) {
    console.warn(`Nao foi possivel enviar o teste gratis por DM a ${discordUserId}: ${error.message}`);
  }
  if (fallbackChannelId) {
    const channel = await client.channels.fetch(fallbackChannelId).catch(() => null);
    if (channel?.isTextBased()) {
      await channel.send(`<@${discordUserId}> seu teste gratis foi criado, mas nao foi possivel enviar a key por mensagem privada. Ative as mensagens diretas e use \`/suporte\`.`);
    }
  }
  return false;
}

async function runFreeTrialFlow(interaction) {
  if (!config.freeTrialEnabled) {
    await interaction.reply({ content: "O teste gratis esta temporariamente indisponivel.", ephemeral: true });
    return;
  }

  await interaction.deferReply({ ephemeral: true });
  const record = await claimFreeTrial({
    discordUserId: interaction.user.id,
    days: config.freeTrialDays
  });
  if (record.existing) {
    await interaction.editReply("Voce ja utilizou o teste gratis desta conta do Discord. Cada usuario pode resgata-lo somente uma vez.");
    return;
  }

  await grantRole(client, interaction.user.id);
  await saveSubscription({
    preapprovalId: record.sourceId,
    discordUserId: interaction.user.id,
    status: "approved",
    active: true,
    kind: "free_trial",
    amount: 0,
    currency: config.currency,
    createdAt: record.createdAt,
    expiresAt: record.expiresAt,
    channelId: interaction.channelId
  });
  await recordSaleSafely({
    sourceId: record.sourceId,
    discordUserId: interaction.user.id,
    kind: "free_trial",
    planName: config.freeTrialName,
    amount: 0,
    currency: config.currency,
    licenseKey: record.licenseKey,
    status: "approved",
    paidAt: record.createdAt,
    expiresAt: record.expiresAt
  });
  const delivered = await notifyFreeTrialApproved(
    interaction.user.id,
    interaction.channelId,
    record.licenseKey,
    record.expiresAt
  );
  await publishLicenseMonitorSafely();
  await sendOperationalLog("Teste gratis liberado", [
    { name: "Usuario", value: `<@${interaction.user.id}>`, inline: true },
    { name: "Validade", value: `${config.freeTrialDays} dia`, inline: true },
    { name: "Entrega por DM", value: delivered ? "Concluida" : "Pendente" }
  ], SUCCESS_COLOR);
  await interaction.editReply(delivered
    ? "✅ Seu teste gratis de 1 dia foi ativado. A key e o link de download foram enviados por mensagem privada."
    : "✅ Seu teste gratis foi ativado, mas sua mensagem privada esta bloqueada. Ative as DMs e use `/suporte` para receber a key.");
}

async function legacySyncSubscription(subscription) {
  const reference = parseDiscordReference(subscription.external_reference);
  if (!reference || reference.guildId !== config.guildId) return;

  const active = subscription.status === "authorized";
  const previous = await findByPreapprovalId(subscription.id);
  await saveSubscription({
    preapprovalId: subscription.id,
    discordUserId: reference.discordUserId,
    status: subscription.status,
    active
  });

  if (active) {
    await grantRole(client, reference.discordUserId);
    const reservation = await reserveKeySafely({
      sourceId: subscription.id,
      paymentId: subscription.id,
      discordUserId: reference.discordUserId
    });
    await recordSaleSafely({
      sourceId: subscription.id,
      paymentId: subscription.id,
      discordUserId: reference.discordUserId,
      planName: config.planName,
      amount: config.planPrice,
      currency: config.currency,
      licenseKey: reservation?.licenseKey,
      status: subscription.status,
      paidAt: subscription.date_created || new Date().toISOString()
    });
    await sendOperationalLog("Assinatura autorizada", [
      { name: "Usuário", value: `<@${reference.discordUserId}>`, inline: true },
      { name: "Referencia", value: subscription.id, inline: true },
      { name: "Status", value: subscription.status, inline: true }
    ], SUCCESS_COLOR);
    if (!previous?.active) {
      await notifyAccessApproved(reference.discordUserId, previous?.channelId, reservation?.licenseKey);
    }
  } else if (["cancelled", "canceled", "paused"].includes(subscription.status)) {
    await revokeRole(client, reference.discordUserId, `Assinatura ${subscription.status}`);
    await updateLicense(subscription.id, "revoke", {
      reason: `Assinatura ${subscription.status}`,
      actor: "mercadopago"
    });
    await recordSaleSafely({
      sourceId: subscription.id,
      paymentId: subscription.id,
      discordUserId: reference.discordUserId,
      planName: config.planName,
      amount: config.planPrice,
      currency: config.currency,
      status: subscription.status
    });
    await sendOperationalLog("Acesso de assinatura removido", [
      { name: "Usuário", value: `<@${reference.discordUserId}>`, inline: true },
      { name: "Status", value: subscription.status, inline: true }
    ], ERROR_COLOR);
  }
}

async function notifyRenewalApproved(discordUserId, expiresAt) {
  const expiration = new Date(expiresAt).toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo" });
  const user = await client.users.fetch(discordUserId);
  await user.send([
    "## ✅ Assinatura renovada!",
    "O pagamento mensal foi confirmado.",
    `Sua key atual continua valida ate **${expiration}**.`,
    "Nao e necessario ativar uma nova key."
  ].join("\n"));
}

async function processAuthorizedInvoice(invoice, subscription = null) {
  const invoiceId = String(invoice?.id || "");
  const paymentId = String(invoice?.payment?.id || "");
  if (!invoiceId || !paymentId || invoice?.payment?.status !== "approved") return false;
  if (processingAuthorizedInvoices.has(invoiceId)) return true;
  processingAuthorizedInvoices.add(invoiceId);

  try {
    if (await findByPaymentId(paymentId)) return true;
    subscription ||= await getSubscription(invoice.preapproval_id);
    const reference = parseDiscordReference(subscription.external_reference || invoice.external_reference);
    if (!reference || reference.guildId !== config.guildId) return false;

    const amountMatches = Number(invoice.transaction_amount) === config.planPrice;
    const currencyMatches = invoice.currency_id === config.currency;
    const planMatches = !config.mercadoPagoPlanId || subscription.preapproval_plan_id === config.mercadoPagoPlanId;
    if (!amountMatches || !currencyMatches || !planMatches) {
      await sendOperationalLog("Fatura de assinatura rejeitada por divergencia", [
        { name: "Fatura", value: invoiceId, inline: true },
        { name: "Valor", value: `${invoice.currency_id} ${invoice.transaction_amount}`, inline: true },
        { name: "Plano correto", value: planMatches ? "Sim" : "Nao", inline: true }
      ], ERROR_COLOR);
      return false;
    }

    const previous = await findByPreapprovalId(subscription.id);
    const processedInvoices = Array.isArray(previous?.processedAuthorizedInvoices)
      ? previous.processedAuthorizedInvoices.map(String)
      : [];
    if (processedInvoices.includes(invoiceId)) return true;
    let license = await getLicense(subscription.id, { reveal: true });
    const renewal = Boolean(processedInvoices.length && license);
    if (!license) {
      const reservation = await reserveKeySafely({
        sourceId: subscription.id,
        paymentId,
        discordUserId: reference.discordUserId
      });
      license = reservation ? {
        licenseKey: reservation.licenseKey,
        expiresAt: reservation.expiresAt
      } : null;
    } else if (renewal) {
      if (license.status === "revoked") {
        const wasExpired = new Date(license.expiresAt).getTime() <= Date.now();
        await updateLicense(subscription.id, "reactivate", {
          days: config.accessDays,
          actor: "mercadopago",
          reason: `Assinatura reativada pela fatura ${invoiceId}`
        });
        if (!wasExpired) {
          await updateLicense(subscription.id, "extend", {
            days: config.accessDays,
            actor: "mercadopago",
            reason: `Fatura recorrente ${invoiceId}`
          });
        }
      } else {
        await updateLicense(subscription.id, "extend", {
          days: config.accessDays,
          actor: "mercadopago",
          reason: `Fatura recorrente ${invoiceId}`
        });
      }
      license = await getLicense(subscription.id, { reveal: true });
    }
    if (!license?.licenseKey) throw new Error("Nao foi possivel preparar a licenca da assinatura");

    await grantRole(client, reference.discordUserId);
    await saveSubscription({
      preapprovalId: subscription.id,
      discordUserId: reference.discordUserId,
      status: "authorized",
      active: true,
      kind: "subscription",
      paymentId,
      amount: Number(invoice.transaction_amount),
      currency: invoice.currency_id,
      expiresAt: license.expiresAt,
      lastAuthorizedInvoiceId: invoiceId,
      lastAuthorizedPaymentId: paymentId,
      processedAuthorizedInvoices: [...new Set([...processedInvoices, invoiceId])].slice(-120)
    });
    await recordSaleSafely({
      sourceId: `invoice:${invoiceId}`,
      paymentId,
      discordUserId: reference.discordUserId,
      kind: "subscription",
      planName: config.planName,
      amount: Number(invoice.transaction_amount),
      currency: invoice.currency_id,
      licenseKey: license.licenseKey,
      status: "approved",
      paidAt: invoice.debit_date || invoice.date_created || new Date().toISOString(),
      expiresAt: license.expiresAt
    });

    if (renewal) {
      await notifyRenewalApproved(reference.discordUserId, license.expiresAt).catch((error) =>
        console.warn(`Falha ao avisar renovacao a ${reference.discordUserId}: ${error.message}`)
      );
    } else {
      await notifyAccessApproved(reference.discordUserId, previous?.channelId, license.licenseKey);
    }
    await publishLicenseMonitorSafely();
    await sendOperationalLog(renewal ? "Assinatura renovada" : "Assinatura paga e liberada", [
      { name: "Usuario", value: `<@${reference.discordUserId}>`, inline: true },
      { name: "Fatura", value: invoiceId, inline: true },
      { name: "Pagamento", value: paymentId, inline: true }
    ], SUCCESS_COLOR);
    return true;
  } finally {
    processingAuthorizedInvoices.delete(invoiceId);
  }
}

async function syncSubscription(subscription) {
  const reference = parseDiscordReference(subscription.external_reference);
  if (!reference || reference.guildId !== config.guildId) return;

  const active = subscription.status === "authorized";
  await saveSubscription({
    preapprovalId: subscription.id,
    discordUserId: reference.discordUserId,
    status: subscription.status,
    active,
    kind: "subscription"
  });

  if (active) {
    const invoices = await getAuthorizedPaymentsBySubscription(subscription.id);
    const approved = (invoices.results || [])
      .filter((item) => item.payment?.status === "approved")
      .sort((a, b) => new Date(a.debit_date || a.date_created) - new Date(b.debit_date || b.date_created));
    for (const invoice of approved) await processAuthorizedInvoice(invoice, subscription);
  } else if (["cancelled", "canceled", "paused"].includes(subscription.status)) {
    await revokeRole(client, reference.discordUserId, `Assinatura ${subscription.status}`);
    await updateLicense(subscription.id, "revoke", {
      reason: `Assinatura ${subscription.status}`,
      actor: "mercadopago"
    });
    await sendOperationalLog("Acesso de assinatura removido", [
      { name: "Usuario", value: `<@${reference.discordUserId}>`, inline: true },
      { name: "Status", value: subscription.status, inline: true }
    ], ERROR_COLOR);
  }
}

function isStaticTestPayment(payment) {
  return payment.status === "approved" &&
    Number(payment.transaction_amount) === config.testPaymentAmount &&
    payment.currency_id === config.currency &&
    (!config.testPaymentReference || payment.external_reference === config.testPaymentReference) &&
    (!config.testPaymentDescription || payment.description === config.testPaymentDescription);
}

async function processStaticTestPayment(payment) {
  if (!config.paymentTestMode || !config.paymentLink || !isStaticTestPayment(payment)) return false;
  if (await findByPaymentId(payment.id)) return true;

  const paidAt = new Date(payment.date_approved || payment.date_created).getTime();
  const candidates = (await findPendingStaticTests())
    .filter((item) => new Date(item.requestedAt || item.updatedAt).getTime() <= paidAt)
    .sort((a, b) => new Date(a.requestedAt || a.updatedAt) - new Date(b.requestedAt || b.updatedAt));

  if (candidates.length !== 1) {
    if (candidates.length > 1) {
      console.warn(`Pagamento de teste ${payment.id} nÃ£o associado: existem ${candidates.length} solicitaÃ§Ãµes pendentes.`);
    }
    return false;
  }

  const pending = candidates[0];
  await grantRole(client, pending.discordUserId);
  await saveSubscription({
    preapprovalId: pending.preapprovalId,
    discordUserId: pending.discordUserId,
    status: "approved",
    active: true,
    kind: "static_test",
    paymentId: String(payment.id),
    amount: Number(payment.transaction_amount),
    currency: payment.currency_id
  });
  const reservation = await reserveKeySafely({
    sourceId: `payment:${payment.id}`,
    paymentId: String(payment.id),
    discordUserId: pending.discordUserId
  });
  await notifyAccessApproved(pending.discordUserId, pending.channelId, reservation?.licenseKey);
  await recordSaleSafely({
    sourceId: `payment:${payment.id}`,
    paymentId: String(payment.id),
    discordUserId: pending.discordUserId,
    planName: "Teste AlbionMKT",
    amount: Number(payment.transaction_amount),
    currency: payment.currency_id,
    licenseKey: reservation?.licenseKey,
    status: payment.status,
    paidAt: payment.date_approved || payment.date_created
  });
  await sendOperationalLog("Pagamento de teste aprovado", [
    { name: "Usuário", value: `<@${pending.discordUserId}>`, inline: true },
    { name: "Pagamento", value: String(payment.id), inline: true },
    { name: "Valor", value: `${payment.currency_id} ${Number(payment.transaction_amount).toFixed(2)}`, inline: true }
  ], SUCCESS_COLOR);
  console.log(`Pagamento estÃ¡tico de teste ${payment.id} aprovado e cargo concedido a ${pending.discordUserId}.`);
  return true;
}

async function processCommercialPayment(payment) {
  const validation = validateCommercialPayment(payment, config.guildId);
  if (!validation.ok) {
    await sendOperationalLog("Pagamento comercial não liberado", [
      { name: "Pagamento", value: String(payment?.id || "não informado"), inline: true },
      { name: "Status", value: String(payment?.status || "não informado"), inline: true },
      { name: "Motivo", value: validation.reason }
    ], ERROR_COLOR);
    return false;
  }

  const { reference, plan } = validation;
  const result = await commercialPaymentGuard.run(
    payment.id,
    async (paymentId) => (await findByPaymentId(paymentId))?.deliveryStatus === "completed",
    async () => {
      const pending = await findByPurchaseId(reference.purchaseId);
      const discordUser = await client.users.fetch(reference.discordUserId).catch(() => null);
      const username = pending?.username || discordUser?.globalName || discordUser?.username || reference.discordUserId;
      const sourceId = `payment:${payment.id}`;
      const reservation = await reserveKeySafely({
        sourceId,
        paymentId: String(payment.id),
        discordUserId: reference.discordUserId,
        username,
        plan
      });
      requireLicenseReservation(reservation);

      await grantRole(client, reference.discordUserId);
      const paidAt = payment.date_approved || payment.date_created || new Date().toISOString();
      await saveSubscription({
        preapprovalId: sourceId,
        purchaseId: reference.purchaseId,
        discordUserId: reference.discordUserId,
        username,
        status: "approved",
        active: true,
        kind: "commercial_payment",
        paymentId: String(payment.id),
        planId: plan.id,
        planName: plan.name,
        amount: plan.price,
        currency: plan.currency,
        purchasedAt: paidAt,
        startsAt: reservation.reservedAt,
        expiresAt: reservation.expiresAt,
        licenseId: reservation.licenseId,
        keyPrefix: `${reservation.licenseKey.slice(0, 14)}...${reservation.licenseKey.slice(-5)}`,
        deliveryStatus: "pending",
        channelId: pending?.channelId || ""
      });

      const delivery = await notifyAccessApproved(
        reference.discordUserId,
        pending?.channelId,
        reservation.licenseKey,
        plan,
        reservation.expiresAt
      );
      await saveSubscription({
        preapprovalId: sourceId,
        deliveryStatus: "completed",
        dmDelivered: delivery.dmDelivered,
        executableDelivery: delivery.downloadPrepared ? "link_preparado" : "indisponível"
      });
      await recordSaleSafely({
        sourceId,
        paymentId: String(payment.id),
        discordUserId: reference.discordUserId,
        username,
        kind: "commercial_payment",
        planId: plan.id,
        planName: plan.name,
        amount: plan.price,
        currency: plan.currency,
        licenseKey: reservation.licenseKey,
        status: "approved",
        paidAt,
        expiresAt: reservation.expiresAt,
        dmDelivered: delivery.dmDelivered,
        executableDelivery: delivery.downloadPrepared ? "link_preparado" : "indisponível"
      });
      await sendOperationalLog("Pagamento aprovado e entregue", [
        { name: "Usuário", value: `<@${reference.discordUserId}>`, inline: true },
        { name: "Plano", value: plan.name, inline: true },
        { name: "Valor", value: `${plan.currency} ${plan.price.toFixed(2)}`, inline: true },
        { name: "Pagamento", value: String(payment.id), inline: true },
        { name: "Mensagem privada", value: delivery.dmDelivered ? "Entregue" : "Bloqueada/falhou", inline: true },
        { name: "Executável", value: delivery.downloadPrepared ? "Link preparado" : "Indisponível", inline: true }
      ], SUCCESS_COLOR);
      await publishLicenseMonitorSafely();
      return true;
    }
  );
  return result.duplicate || Boolean(result.value);
}

async function pollStaticTestPayments() {
  if (!config.paymentTestMode || !config.paymentLink) return;
  try {
    const pending = await findPendingStaticTests();
    if (pending.length !== 1) return;
    const response = await getRecentPayments(20);
    for (const payment of response.results || []) {
      if (await processStaticTestPayment(payment)) break;
    }
  } catch (error) {
    console.error("Falha ao consultar pagamentos de teste:", error);
  }
}

app.get("/health", (_req, res) => res.json({ ok: true }));
async function handleLicenseApi(req, res, activate) {
  res.set("Cache-Control", "no-store");
  if (!allowLicenseApiRequest(req.ip || req.socket.remoteAddress || "unknown")) {
    res.status(429).json({ valid: false, code: "RATE_LIMIT", message: "Muitas tentativas. Aguarde um minuto." });
    return;
  }
  const licenseKey = String(req.body?.key || req.body?.licenseKey || "").trim();
  const hwid = String(req.body?.hwid || "").trim();
  const appVersion = String(req.body?.appVersion || "").trim();
  if (!licenseKey || licenseKey.length > 100 || !hwid || hwid.length > 300 || appVersion.length > 50) {
    res.status(400).json({ valid: false, code: "INVALID_REQUEST", message: "Dados de licenca invalidos." });
    return;
  }
  try {
    const result = await validateLicense({ licenseKey, hwid, appVersion, activate });
    if (result.valid && result.newlyActivated) await publishLicenseMonitorSafely();
    res.status(result.valid ? 200 : 403).json(result);
  } catch (error) {
    console.error("Falha na API de licencas:", error);
    res.status(500).json({ valid: false, code: "SERVER_ERROR", message: "Falha temporaria ao validar licenca." });
  }
}

app.post("/api/licenses/activate", (req, res) => handleLicenseApi(req, res, true));
app.post("/api/licenses/validate", (req, res) => handleLicenseApi(req, res, false));
app.get("/download/albionmkt", (req, res) => {
  const user = String(req.query.user || "");
  const expires = String(req.query.expires || "");
  const supplied = String(req.query.signature || "");
  if (!/^\d+$/.test(user) || !/^\d+$/.test(expires) || !/^[a-f0-9]{64}$/.test(supplied)) {
    res.status(403).send("Link de download inv\u00e1lido.");
    return;
  }
  if (Number(expires) < Math.floor(Date.now() / 1000)) {
    res.status(410).send("Este link expirou. Solicite um novo link no Discord.");
    return;
  }
  const expected = crypto
    .createHmac("sha256", config.downloadSecret)
    .update(`${user}:${expires}`)
    .digest("hex");
  const valid = supplied.length === expected.length && crypto.timingSafeEqual(
    Buffer.from(supplied, "hex"),
    Buffer.from(expected, "hex")
  );
  if (!valid || !config.downloadFilePath) {
    res.status(403).send("Link de download inv\u00e1lido.");
    return;
  }
  res.download(config.downloadFilePath, "MKT_Setup_2.7.1.exe");
});
app.get("/retorno", (_req, res) => {
  res.type("html").send(`<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AlbionMKT - assinatura recebida</title>
<style>body{font-family:system-ui;background:#0b2239;color:#f6e4be;display:grid;place-items:center;min-height:100vh;margin:0}.card{max-width:560px;margin:24px;padding:32px;border-radius:18px;background:#102d49;box-shadow:0 20px 60px #0006}h1{color:#fff}p{line-height:1.6}.ok{color:#67d391;font-weight:700}</style></head>
<body><main class="card"><div class="ok">Pagamento em confirmacao</div><h1>Recebemos o retorno da sua assinatura</h1>
<p>O bot está consultando o Mercado Pago de forma segura. Assim que o pagamento do plano escolhido for confirmado, sua key, cargo e link de download serão enviados por mensagem privada no Discord.</p>
<p>Voce ja pode fechar esta pagina e voltar ao Discord. Nao e necessario atualizar ou abrir este link novamente.</p></main></body></html>`);
});

app.get("/webhooks/mercadopago", (_req, res) => {
  res.json({
    ok: true,
    message: "Webhook AlbionMKT ativo. As notificações do Mercado Pago devem usar POST."
  });
});

app.post("/webhooks/mercadopago", async (req, res) => {
  res.sendStatus(200);
  const type = req.body?.type || req.query.type || req.body?.topic;
  const testPaymentNotification = config.paymentTestMode && type === "payment";
  if (!verifyWebhook(req) && !testPaymentNotification) {
    console.warn("Webhook rejeitado: assinatura inválida.");
    return;
  }

  try {
    const id = req.body?.data?.id || req.query["data.id"] || req.query.id;
    if (!id) return;

    if (["subscription_authorized_payment", "authorized_payment"].includes(type)) {
      const invoice = await getAuthorizedPayment(id);
      await processAuthorizedInvoice(invoice);
    } else if (["subscription_preapproval", "preapproval"].includes(type)) {
      await syncSubscription(await getSubscription(id));
    } else if (type === "payment") {
      const payment = await getPayment(id);
      if (String(payment.external_reference || "").startsWith("albionmkt:v1:")) {
        await processCommercialPayment(payment);
        return;
      }
      if (payment.status !== "approved") return;
      if (!config.paymentTestMode) {
        const invoices = await getAuthorizedPaymentsByPayment(payment.id);
        const invoice = (invoices.results || []).find((item) => item.payment?.status === "approved");
        if (invoice && await processAuthorizedInvoice(invoice)) return;
      }
      if (await findByPaymentId(payment.id)) return;
      const reference = parseDiscordReference(payment.external_reference);
      if (reference?.guildId === config.guildId) {
        const amountMatches = Number(payment.transaction_amount) === config.planPrice;
        const currencyMatches = payment.currency_id === config.currency;
        if (!amountMatches || !currencyMatches) {
          console.warn(`Pagamento ${payment.id} rejeitado: valor ou moeda divergente.`);
          await sendOperationalLog("Pagamento rejeitado por divergencia", [
            { name: "Pagamento", value: String(payment.id), inline: true },
            { name: "Valor recebido", value: `${payment.currency_id} ${payment.transaction_amount}`, inline: true }
          ], ERROR_COLOR);
          return;
        }
        await grantRole(client, reference.discordUserId);
        await saveSubscription({
          preapprovalId: `payment:${payment.id}`,
          discordUserId: reference.discordUserId,
          status: payment.status,
          active: true,
          kind: "payment",
          paymentId: String(payment.id),
          amount: Number(payment.transaction_amount),
          currency: payment.currency_id
        });
        const records = await findByDiscordUser(reference.discordUserId);
        const pending = records
          .filter((item) => !item.active || item.kind === "payment_preference")
          .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))[0];
        const reservation = await reserveKeySafely({
          sourceId: `payment:${payment.id}`,
          paymentId: String(payment.id),
          discordUserId: reference.discordUserId
        });
        await notifyAccessApproved(reference.discordUserId, pending?.channelId, reservation?.licenseKey);
        await recordSaleSafely({
          sourceId: `payment:${payment.id}`,
          paymentId: String(payment.id),
          discordUserId: reference.discordUserId,
          planName: config.planName,
          amount: Number(payment.transaction_amount),
          currency: payment.currency_id,
          licenseKey: reservation?.licenseKey,
          status: payment.status,
          paidAt: payment.date_approved || payment.date_created
        });
        await sendOperationalLog("Pagamento aprovado", [
          { name: "Usuário", value: `<@${reference.discordUserId}>`, inline: true },
          { name: "Pagamento", value: String(payment.id), inline: true },
          { name: "Valor", value: `${payment.currency_id} ${Number(payment.transaction_amount).toFixed(2)}`, inline: true }
        ], SUCCESS_COLOR);
        console.log(`Pagamento ${payment.id} aprovado e cargo concedido a ${reference.discordUserId}.`);
      } else {
        await processStaticTestPayment(payment);
      }
    }
  } catch (error) {
    console.error("Falha ao processar webhook:", error);
  }
});

async function runCommercialPaymentFlow(interaction, email, planId) {
  if (!config.salesEnabled) {
    await interaction.reply({ content: "Os pagamentos estão temporariamente em manutenção.", ephemeral: true });
    return;
  }
  const plan = requireCommercialPlan(planId);
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(email || "").trim())) {
    await interaction.reply({ content: "Informe um e-mail válido para gerar o checkout.", ephemeral: true });
    return;
  }
  await interaction.deferReply({ ephemeral: true });
  const existing = await findByDiscordUser(interaction.user.id);
  if (existing.some((item) => item.active && (!item.expiresAt || new Date(item.expiresAt) > new Date()))) {
    await interaction.editReply("Você já possui um acesso ativo. Consulte **Minha assinatura** ou use `/suporte` antes de realizar outra compra.");
    return;
  }
  const purchaseId = createPurchaseId();
  const preference = await createPaymentPreference({
    discordUserId: interaction.user.id,
    email: String(email).trim(),
    planId: plan.id,
    purchaseId
  });
  const requestedAt = new Date().toISOString();
  await saveSubscription({
    preapprovalId: preference.id,
    purchaseId,
    discordUserId: interaction.user.id,
    username: interaction.user.globalName || interaction.user.username,
    status: "pending",
    active: false,
    kind: "commercial_preference",
    planId: plan.id,
    planName: plan.name,
    amount: plan.price,
    currency: plan.currency,
    email: String(email).trim(),
    requestedAt,
    channelId: interaction.channelId
  });
  await interaction.editReply([
    `## ${plan.name} — AlbionMKT`,
    `Valor: **${formatPlanPrice(plan)}**`,
    `Acesso: **${plan.days} dias**`,
    "",
    "Este checkout foi criado exclusivamente para sua conta do Discord:",
    preference.init_point,
    "",
    "Após a aprovação, cargo, key e link temporário de download serão enviados automaticamente por mensagem privada."
  ].join("\n"));
}

async function runSubscriptionFlow(interaction, email, planId) {
  return runCommercialPaymentFlow(interaction, email, planId);
}

async function runPixPaymentFlow(interaction, email, planId) {
  return runCommercialPaymentFlow(interaction, email, planId);
}

async function showSubscriptionStatus(interaction) {
  await interaction.deferReply({ ephemeral: true });
  const records = await findByDiscordUser(interaction.user.id);
  const latest = records.sort((a, b) => new Date(b.updatedAt || b.requestedAt || 0) - new Date(a.updatedAt || a.requestedAt || 0))[0];
  if (!latest) {
    await interaction.editReply("Nenhuma assinatura encontrada. Escolha **Venda**, **Compra** ou **MKT Completo** no painel de planos.");
    return;
  }

  if (!latest.active) {
    await interaction.editReply([
      "## Situação da assinatura",
      `**Plano:** ${latest.planName || config.planName}`,
      `**Situação:** ${latest.status === "pending" ? "Pagamento pendente" : latest.status || "Inativa"}`,
      `**Solicitada em:** ${formatLicenseDate(latest.requestedAt || latest.updatedAt)}`,
      "",
      "Se o pagamento já foi concluído, aguarde a confirmação do Mercado Pago. Caso precise, use `/suporte`."
    ].join("\n"));
    return;
  }

  const licenseIdentifier = latest.licenseId || (latest.paymentId ? `payment:${latest.paymentId}` : latest.preapprovalId);
  const license = await getLicense(licenseIdentifier, { reveal: true }).catch(() => null);
  const purchasedAt = latest.purchasedAt || latest.createdAt || latest.updatedAt;
  const startsAt = latest.startsAt || license?.createdAt || purchasedAt;
  const expiresAt = latest.expiresAt || license?.expiresAt;
  const remaining = expiresAt ? Math.max(0, Math.ceil((new Date(expiresAt).getTime() - Date.now()) / 86_400_000)) : 0;
  const active = latest.active && (!expiresAt || remaining > 0) && license?.effectiveStatus !== "revoked";
  const downloadLink = createDownloadLink(interaction.user.id);
  await interaction.editReply([
    "## Minha assinatura AlbionMKT",
    `**Plano contratado:** ${latest.planName || license?.planName || config.planName}`,
    `**Situação:** ${active ? "Ativa" : "Expirada ou inativa"}`,
    `**Data da compra:** ${formatLicenseDate(purchasedAt)}`,
    `**Data de início:** ${formatLicenseDate(startsAt)}`,
    `**Data de vencimento:** ${formatLicenseDate(expiresAt)}`,
    `**Dias restantes:** ${remaining}`,
    `**Key vinculada:** ${license?.licenseKey ? `\`${license.licenseKey}\`` : "Consulte o suporte"}`,
    "",
    downloadLink ? `**Baixar o programa:** ${downloadLink}` : "**Download:** temporariamente indisponível.",
    downloadLink ? `O link é pessoal e válido por ${config.downloadLinkDays} dias.` : "",
    "",
    "Precisa de ajuda? Use `/suporte` para abrir um atendimento privado."
  ].filter(Boolean).join("\n"));
}

async function handleButtonInteraction(interaction) {
  const commercialPlans = {
    [UI_IDS.commercialPurchase]: "purchase",
    [UI_IDS.commercialSales]: "sales",
    [UI_IDS.commercialComplete]: "complete"
  };
  if (commercialPlans[interaction.customId]) {
    await interaction.showModal(commercialPaymentModal(commercialPlans[interaction.customId]));
    return;
  }
  if (interaction.customId === UI_IDS.onboardingStart) {
    const isGuidedMessage = interaction.message.embeds.some((embed) =>
      embed.footer?.text?.includes("Introdução")
    );
    if (isGuidedMessage) await interaction.update(onboardingStep("start"));
    else await interaction.reply({ ...onboardingStep("start"), ephemeral: true });
    return;
  }
  if (interaction.customId === UI_IDS.onboardingFeatures) {
    await interaction.update(onboardingStep("features"));
    return;
  }
  if (interaction.customId === UI_IDS.onboardingPlan) {
    const payload = onboardingStep("plan");
    const isGuidedMessage = interaction.message.embeds.some((embed) =>
      embed.footer?.text?.includes("Introdução")
    );
    if (isGuidedMessage) await interaction.update(payload);
    else await interaction.reply({ ...payload, ephemeral: true });
    return;
  }
  if (interaction.customId === UI_IDS.onboardingTerms) {
    await interaction.update(onboardingStep("terms"));
    return;
  }
  if (interaction.customId === UI_IDS.onboardingAccept) {
    await interaction.deferUpdate();
    const role = await grantVisitorRole(client, interaction.user.id);
    await saveOnboardingAcceptance({
      discordUserId: interaction.user.id,
      username: interaction.user.globalName || interaction.user.username,
      termsVersion: "v1",
      roleId: role.id
    });
    await sendOperationalLog("Introdução concluída", [
      { name: "Usuário", value: `<@${interaction.user.id}>`, inline: true },
      { name: "Cargo", value: `<@&${role.id}>`, inline: true },
      { name: "Termos", value: "v1", inline: true }
    ], BRAND.success);
    await interaction.editReply({
      embeds: [new EmbedBuilder()
        .setColor(BRAND.success)
        .setTitle("Acesso público liberado")
        .setDescription([
          "Sua introdução foi concluída com sucesso.",
          "",
          `Conheça os recursos em <#${SERVER_IDS.channels.resources}>.`,
          `Consulte o plano em <#${SERVER_IDS.channels.sales}>.`,
          `Veja respostas rápidas em <#${SERVER_IDS.channels.faq}>.`
        ].join("\n"))],
      components: []
    });
    return;
  }
  if (interaction.customId === UI_IDS.onboardingHelp || interaction.customId === UI_IDS.supportOpen) {
    await interaction.showModal(supportModal());
    return;
  }
  if (interaction.customId === UI_IDS.freeTrial) {
    await runFreeTrialFlow(interaction);
    return;
  }
  if (interaction.customId === UI_IDS.salesOpen) {
    await interaction.showModal(salesModal());
    return;
  }
  if (interaction.customId === UI_IDS.pixOpen) {
    await interaction.showModal(pixPaymentModal());
    return;
  }
  if (interaction.customId === UI_IDS.subscriptionStatus) {
    await showSubscriptionStatus(interaction);
  }
}

async function handleModalInteraction(interaction) {
  if (interaction.customId.startsWith("commercial:checkout:")) {
    const planId = interaction.customId.slice("commercial:checkout:".length);
    const email = interaction.fields.getTextInputValue(UI_IDS.commercialEmail).trim();
    await runCommercialPaymentFlow(interaction, email, planId);
    return;
  }
  if (interaction.customId === UI_IDS.salesModal) {
    const email = interaction.fields.getTextInputValue(UI_IDS.salesEmail).trim();
    await runSubscriptionFlow(interaction, email, "sales");
    return;
  }
  if (interaction.customId === UI_IDS.pixModal) {
    const email = interaction.fields.getTextInputValue(UI_IDS.salesEmail).trim();
    await runPixPaymentFlow(interaction, email, "sales");
    return;
  }
  if (interaction.customId === UI_IDS.supportModal) {
    const subject = interaction.fields.getTextInputValue(UI_IDS.supportSubject).trim();
    const subscriberRole = interaction.guild?.roles.cache.get(config.subscriberRoleId);
    const isSubscriber = Boolean(subscriberRole && interaction.member?.roles?.cache?.has(subscriberRole.id));
    const parentId = isSubscriber ? config.supportChannelId : config.entryChannelId;
    await openSupportTicket(interaction, subject, parentId);
  }
}

client.on("interactionCreate", async (interaction) => {
  if (interaction.isButton()) {
    try {
      await handleButtonInteraction(interaction);
    } catch (error) {
      console.error("Falha em botão:", error);
      const message = "Não foi possível concluir esta ação. Tente novamente ou abra um atendimento.";
      if (interaction.deferred || interaction.replied) await interaction.editReply({ content: message, embeds: [], components: [] }).catch(() => null);
      else await interaction.reply({ content: message, ephemeral: true }).catch(() => null);
    }
    return;
  }
  if (interaction.isModalSubmit()) {
    try {
      await handleModalInteraction(interaction);
    } catch (error) {
      console.error("Falha em formulário:", error);
      const message = "Não foi possível concluir esta ação. Tente novamente ou contate a equipe.";
      if (interaction.deferred || interaction.replied) await interaction.editReply(message).catch(() => null);
      else await interaction.reply({ content: message, ephemeral: true }).catch(() => null);
    }
    return;
  }
  if (!interaction.isChatInputCommand()) return;

  try {
    if (interaction.commandName === "suporte") {
      await openSupportTicket(interaction);
      return;
    }

    if (interaction.commandName === "fechar-suporte") {
      await closeSupportTicket(interaction);
      return;
    }

    if (interaction.commandName === "publicar-paineis") {
      if (!interaction.memberPermissions?.has(PermissionFlagsBits.ManageGuild)) {
        await interaction.reply({ content: "Você não possui permissão para atualizar os painéis.", ephemeral: true });
        return;
      }
      await interaction.deferReply({ ephemeral: true });
      const messageIds = await publishPanels(client);
      await interaction.editReply(`Painéis atualizados com sucesso (${messageIds.length}).`);
      return;
    }

    if (interaction.commandName === "relatorio-vendas") {
      if (!interaction.memberPermissions?.has(PermissionFlagsBits.ManageGuild)) {
        await interaction.reply({ content: "Você não possui permissão para exportar vendas.", ephemeral: true });
        return;
      }
      await interaction.deferReply({ ephemeral: true });
      const attachment = await createSalesCsvAttachment();
      await interaction.editReply({
        content: "Relatório privado de vendas do AlbionMKT:",
        files: [attachment]
      });
      return;
    }

    if (interaction.commandName === "estoque-keys") {
      if (!interaction.memberPermissions?.has(PermissionFlagsBits.ManageGuild)) {
        await interaction.reply({ content: "Você não possui permissão para consultar o estoque.", ephemeral: true });
        return;
      }
      await interaction.deferReply({ ephemeral: true });
      const stats = await getLicenseStats();
      await interaction.editReply([
        "**Painel de licencas do AlbionMKT**",
        `Ativas: **${stats.active}**`,
        `Vencem em ate 7 dias: **${stats.expiring}**`,
        `Expiradas: **${stats.expired}**`,
        `Revogadas: **${stats.revoked}**`,
        `Computadores vinculados: **${stats.devices}**`,
        `Total criado: **${stats.total}**`
      ].join("\n"));
      return;
    }

    if (interaction.commandName === "licenca-criar") {
      if (!interaction.memberPermissions?.has(PermissionFlagsBits.ManageGuild)) {
        await interaction.reply({ content: "Voce nao possui permissao para criar licencas.", ephemeral: true });
        return;
      }
      await interaction.deferReply({ ephemeral: true });
      const customer = interaction.options.getUser("cliente", true);
      const days = interaction.options.getInteger("dias", true);
      const access = interaction.options.getString("acesso", true);
      const modules = modulesForAccess(access);
      const maxDevices = interaction.options.getInteger("computadores") || 1;
      const note = interaction.options.getString("observacao") || "Criada manualmente no Discord";
      const record = await createLicense({
        sourceId: `discord:${interaction.id}`,
        discordUserId: customer.id,
        days,
        maxDevices,
        modules,
        note,
        actor: interaction.user.id
      });
      let delivered = true;
      await customer.send([
        "**Sua licenca do AlbionMKT foi criada**",
        `Key: \`${record.licenseKey}\``,
        `Valida ate: **${formatLicenseDate(record.expiresAt)}**`,
        `Acesso: **${formatLicenseModules(record.modules)}**`,
        `Computadores permitidos: **${record.maxDevices}**`,
        "Nao compartilhe esta key."
      ].join("\n")).catch(() => { delivered = false; });
      await interaction.editReply([
        "**Licenca criada com sucesso.**",
        licenseSummary(record),
        delivered ? "A key completa foi enviada por mensagem privada ao cliente." : `Nao foi possivel enviar DM. Entregue esta key com seguranca: \`${record.licenseKey}\``
      ].join("\n\n"));
      await sendOperationalLog("Licenca criada manualmente", [
        { name: "Cliente", value: `<@${customer.id}>`, inline: true },
        { name: "Validade", value: `${days} dias`, inline: true },
        { name: "Acesso", value: formatLicenseModules(record.modules), inline: true },
        { name: "Key", value: record.keyPrefix, inline: true }
      ], SUCCESS_COLOR);
      await publishLicenseMonitorSafely();
      return;
    }

    if (interaction.commandName === "licencas") {
      if (!interaction.memberPermissions?.has(PermissionFlagsBits.ManageGuild)) {
        await interaction.reply({ content: "Voce nao possui permissao para consultar licencas.", ephemeral: true });
        return;
      }
      await interaction.deferReply({ ephemeral: true });
      const stats = await getLicenseStats();
      const upcoming = (await listLicenses())
        .filter((item) => item.effectiveStatus === "active")
        .sort((a, b) => new Date(a.expiresAt) - new Date(b.expiresAt))
        .slice(0, 10);
      await interaction.editReply([
        "**Monitor de licencas AlbionMKT**",
        `Ativas **${stats.active}** | Em 7 dias **${stats.expiring}** | Expiradas **${stats.expired}** | Revogadas **${stats.revoked}**`,
        "",
        "**Proximos vencimentos**",
        ...(upcoming.length ? upcoming.map((item) => `• \`${item.keyPrefix}\` - ${formatLicenseDate(item.expiresAt)} - ${item.discordUserId ? `<@${item.discordUserId}>` : "sem cliente"}`) : ["Nenhuma licenca ativa."])
      ].join("\n"));
      return;
    }

    if (interaction.commandName === "licenca-info") {
      if (!interaction.memberPermissions?.has(PermissionFlagsBits.ManageGuild)) {
        await interaction.reply({ content: "Voce nao possui permissao para consultar licencas.", ephemeral: true });
        return;
      }
      const record = await getLicense(interaction.options.getString("licenca", true));
      await interaction.reply({ content: record ? `**Detalhes da licenca**\n${licenseSummary(record)}` : "Licenca nao encontrada.", ephemeral: true });
      return;
    }

    if (interaction.commandName === "licenca-entregar") {
      if (!interaction.memberPermissions?.has(PermissionFlagsBits.ManageGuild)) {
        await interaction.reply({ content: "Voce nao possui permissao para entregar licencas.", ephemeral: true });
        return;
      }
      await interaction.deferReply({ ephemeral: true });
      const record = await getLicense(interaction.options.getString("licenca", true), { reveal: true });
      if (!record) {
        await interaction.editReply("Licenca nao encontrada.");
        return;
      }
      if (!record.discordUserId) {
        await interaction.editReply("Esta licenca nao possui um cliente do Discord vinculado.");
        return;
      }
      const customer = await client.users.fetch(record.discordUserId);
      const delivered = await customer.send([
        "**Sua licenca do AlbionMKT**",
        `Key: \`${record.licenseKey}\``,
        `Valida ate: **${formatLicenseDate(record.expiresAt)}**`,
        `Acesso: **${formatLicenseModules(record.modules)}**`,
        `Computadores permitidos: **${record.maxDevices}**`,
        "Nao compartilhe esta key."
      ].join("\n")).then(() => true).catch(() => false);
      await interaction.editReply(delivered
        ? `Licenca \`${record.keyPrefix}\` enviada por DM para <@${record.discordUserId}>.`
        : "Nao foi possivel enviar a mensagem privada. O cliente precisa habilitar DMs do servidor.");
      return;
    }

    if (interaction.commandName === "licenca-modulos") {
      if (!interaction.memberPermissions?.has(PermissionFlagsBits.ManageGuild)) {
        await interaction.reply({ content: "Voce nao possui permissao para alterar os bots da licenca.", ephemeral: true });
        return;
      }
      const modules = modulesForAccess(interaction.options.getString("acesso", true));
      const record = await updateLicense(
        interaction.options.getString("licenca", true),
        "set-modules",
        { modules, actor: interaction.user.id }
      );
      if (record) await publishLicenseMonitorSafely();
      await interaction.reply({
        content: record ? `Acesso atualizado para **${formatLicenseModules(record.modules)}**.\n${licenseSummary(record)}` : "Licenca nao encontrada.",
        ephemeral: true
      });
      return;
    }

    if (["licenca-estender", "licenca-revogar", "licenca-reativar", "licenca-resetar-pc"].includes(interaction.commandName)) {
      if (!interaction.memberPermissions?.has(PermissionFlagsBits.ManageGuild)) {
        await interaction.reply({ content: "Voce nao possui permissao para alterar licencas.", ephemeral: true });
        return;
      }
      const actions = {
        "licenca-estender": "extend",
        "licenca-revogar": "revoke",
        "licenca-reativar": "reactivate",
        "licenca-resetar-pc": "reset-devices"
      };
      const record = await updateLicense(
        interaction.options.getString("licenca", true),
        actions[interaction.commandName],
        {
          days: interaction.options.getInteger("dias") || 0,
          reason: interaction.options.getString("motivo") || "",
          actor: interaction.user.id
        }
      );
      if (record) await publishLicenseMonitorSafely();
      await interaction.reply({
        content: record ? `**Licenca atualizada com sucesso.**\n${licenseSummary(record)}` : "Licenca nao encontrada.",
        ephemeral: true
      });
      return;
    }

    if (interaction.commandName === "ajuda") {
      await interaction.reply({
        content: [
          "**AlbionMKT - Ajuda**",
          "- `/status`: consulte o estado do bot e das vendas.",
          "- `/teste-gratis`: receba uma key gratis de 1 dia, uma unica vez.",
          "- `/assinar`: escolha Venda, Compra ou MKT Completo e gere seu checkout individual.",
          "- `/pagar-pix`: gere o mesmo checkout individual com Pix selecionado.",
          "- `/minha-assinatura`: consulte uma assinatura existente.",
          "- `/suporte`: abra um atendimento privado com a equipe.",
          "- `/fechar-suporte`: encerre o atendimento atual."
        ].join("\n"),
        ephemeral: true
      });
      return;
    }

    if (interaction.commandName === "status") {
      await interaction.reply({
        content: [
          "**Status do AlbionMKT**",
          "🟢 Bot: online",
          config.paymentTestMode
            ? "🟢 Checkout individual: modo de teste"
            : config.paymentLink
            ? "🟢 Link de pagamento: disponível"
            : config.salesEnabled
              ? "🟢 Vendas: abertas"
              : "🟡 Vendas: em configuração",
          config.paymentTestMode
            ? "🟢 Liberação automática: ativa para o teste"
            : config.salesEnabled
            ? "🟢 Liberação automática: ativa"
            : "🟡 Liberação automática: em configuração"
        ].join("\n"),
        ephemeral: true
      });
      return;
    }

    if (interaction.commandName === "teste-gratis") {
      await runFreeTrialFlow(interaction);
      return;
    }

    if (interaction.commandName === "assinar") {
      await runSubscriptionFlow(
        interaction,
        interaction.options.getString("email", true),
        interaction.options.getString("plano", true)
      );
      return;

      if (config.paymentTestMode) {
        if (config.paymentLink) {
          const pendingTests = await findPendingStaticTests();
          const ownPending = pendingTests.find((item) => item.discordUserId === interaction.user.id);
          if (pendingTests.length && !ownPending) {
            await interaction.reply({
              content: "Existe outro teste de pagamento em andamento. Aguarde a conclusao antes de iniciar o seu.",
              ephemeral: true
            });
            return;
          }
          const email = interaction.options.getString("email", true);
          const requestedAt = new Date().toISOString();
          await saveSubscription({
            preapprovalId: `static-test:${interaction.user.id}`,
            discordUserId: interaction.user.id,
            status: "pending",
            active: false,
            kind: "static_test",
            email,
            requestedAt,
            channelId: interaction.channelId,
            paymentId: null
          });
          await interaction.reply({
            content: [
              "**AlbionMKT - pagamento de teste automatico**",
              `Valor do teste: **R$ ${config.testPaymentAmount.toFixed(2).replace(".", ",")}**`,
              "",
              `Pague por este link: ${config.paymentLink}`,
              "",
              "Depois da aprovacao, o bot consultara o Mercado Pago e concedera o cargo `Assinante` automaticamente."
            ].join("\n"),
            ephemeral: true
          });
          return;
        }
        await interaction.deferReply({ ephemeral: true });
        const email = interaction.options.getString("email", true);
        const preference = await createPaymentPreference({
          discordUserId: interaction.user.id,
          email
        });
        await saveSubscription({
          preapprovalId: preference.id,
          discordUserId: interaction.user.id,
          status: "pending",
          active: false,
          kind: "payment_preference",
          email,
          channelId: interaction.channelId
        });
        await interaction.editReply([
          `**${config.planName} — AlbionMKT (teste automático)**`,
          `Valor: **R$ ${config.planPrice.toFixed(2).replace(".", ",")}**`,
          `Acesso: **${config.accessDays} dias**`,
          "",
          "Este checkout foi criado exclusivamente para sua conta do Discord:",
          preference.init_point,
          "",
          "Após a aprovação do pagamento, o cargo `Assinante` será concedido automaticamente."
        ].join("\n"));
        return;
      }

      if (config.paymentLink) {
        const email = interaction.options.getString("email", true);
        await interaction.reply({
          content: [
            `**${config.planName} — AlbionMKT**`,
            `Valor: **R$ ${config.planPrice.toFixed(2).replace(".", ",")}/mês**`,
            `Acesso: **${config.accessDays} dias**`,
            "",
            `Pague pelo Mercado Pago: ${config.paymentLink}`,
            "",
            `Utilize no pagamento o mesmo e-mail informado no comando: **${email}**.`,
            "A liberação automática ainda está em configuração; o pagamento será conferido antes da entrega do acesso."
          ].join("\n"),
          ephemeral: true
        });
        return;
      }

      if (!config.salesEnabled) {
        await interaction.reply({
          content: "As assinaturas estão temporariamente em manutenção. Tente novamente mais tarde.",
          ephemeral: true
        });
        return;
      }

      await interaction.deferReply({ ephemeral: true });
      const existing = await findByDiscordUser(interaction.user.id);
      if (existing.some((item) => item.active)) {
        await interaction.editReply("Você já possui uma assinatura ativa.");
        return;
      }

      const subscription = await createSubscription({
        discordUserId: interaction.user.id,
        email: interaction.options.getString("email", true)
      });
      await saveSubscription({
        preapprovalId: subscription.id,
        discordUserId: interaction.user.id,
        status: subscription.status,
        active: false,
        channelId: interaction.channelId
      });
      await interaction.editReply(
        `Finalize sua assinatura de **${config.planName}** por **R$ ${config.planPrice.toFixed(2).replace(".", ",")}/mês**:\n${subscription.init_point}`
      );
    }

    if (interaction.commandName === "pagar-pix") {
      await runPixPaymentFlow(
        interaction,
        interaction.options.getString("email", true),
        interaction.options.getString("plano", true)
      );
      return;
    }

    if (interaction.commandName === "minha-assinatura") {
      await showSubscriptionStatus(interaction);
      return;

      await interaction.deferReply({ ephemeral: true });
      const records = await findByDiscordUser(interaction.user.id);
      const latest = records.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))[0];
      if (!latest) {
        await interaction.editReply("Nenhuma assinatura encontrada. Use `/assinar`.");
        return;
      }
      if (latest.kind === "payment" || latest.kind === "payment_preference") {
        await interaction.editReply(
          latest.active
            ? "Pagamento aprovado e acesso **Assinante** ativo."
            : "Pagamento ainda pendente de aprovação."
        );
        return;
      }
      const remote = await getSubscription(latest.preapprovalId);
      await syncSubscription(remote);
      await interaction.editReply(`Estado atual da assinatura: **${remote.status}**.`);
    }
  } catch (error) {
    console.error(error);
    const message = "Não foi possível concluir a operação. Tente novamente ou contate o suporte.";
    if (interaction.deferred || interaction.replied) await interaction.editReply(message);
    else await interaction.reply({ content: message, ephemeral: true });
  }
});

client.once("clientReady", async () => {
  client.user.setPresence({
    activities: [{ name: "AlbionMKT | /ajuda", type: ActivityType.Watching }],
    status: "online"
  });
  const guild = await client.guilds.fetch(config.guildId);
  const me = await guild.members.fetchMe();
  if (!me.permissions.has(PermissionFlagsBits.ManageRoles)) {
    console.warn("O bot não possui a permissão Gerenciar Cargos.");
  }
  console.log(`Bot conectado como ${client.user.tag}.`);
  const importedLicenses = await migrateLegacyLicenses();
  if (importedLicenses) console.log(`${importedLicenses} licenca(s) anterior(es) importada(s).`);
  await publishLicenseMonitorSafely();
  await publishPanels(client).catch((error) =>
    console.error("Falha ao atualizar os paineis oficiais:", error)
  );
  await seedSalesLedger();
  await processRenewalReminders(client, sendOperationalLog).catch((error) =>
    console.error("Falha ao processar lembretes de renovação:", error)
  );
  setInterval(() => {
    processRenewalReminders(client, sendOperationalLog).catch((error) =>
      console.error("Falha ao processar lembretes de renovação:", error)
    );
    publishLicenseMonitorSafely();
  }, 60 * 60 * 1000).unref();
  setInterval(pollStaticTestPayments, 10_000).unref();
  await pollStaticTestPayments();
});

app.listen(config.port, "127.0.0.1", () =>
  console.log(`Webhook ouvindo em 127.0.0.1:${config.port}.`)
);
await client.login(config.discordToken);
