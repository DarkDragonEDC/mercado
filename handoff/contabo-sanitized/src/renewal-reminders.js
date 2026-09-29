import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";
import { EmbedBuilder } from "discord.js";
import { config } from "./config.js";
import { listSales, publishSalesTable, saveSale } from "./sales-ledger.js";
import { revokeRole } from "./discord-access.js";

const stateFile = path.resolve("data", "renewal-reminders.json");
const ACTIVE_STATUSES = new Set(["approved", "authorized"]);
const DAY = 86_400_000;
let running = false;

async function loadState() {
  try {
    return JSON.parse(await readFile(stateFile, "utf8"));
  } catch (error) {
    if (error.code === "ENOENT") return {};
    throw error;
  }
}

async function saveState(state) {
  await mkdir(path.dirname(stateFile), { recursive: true });
  const temporary = `${stateFile}.tmp`;
  await writeFile(temporary, JSON.stringify(state, null, 2), "utf8");
  await rename(temporary, stateFile);
}

function expirationOf(sale) {
  const explicit = new Date(sale.expiresAt || "");
  if (!Number.isNaN(explicit.getTime())) return explicit;
  const paidAt = new Date(sale.paidAt || sale.updatedAt || "");
  if (Number.isNaN(paidAt.getTime())) return null;
  return new Date(paidAt.getTime() + config.accessDays * DAY);
}

function latestActiveSales(sales) {
  const latest = new Map();
  for (const sale of sales) {
    if (!sale.discordUserId || !ACTIVE_STATUSES.has(String(sale.status).toLowerCase())) continue;
    const expiresAt = expirationOf(sale);
    if (!expiresAt) continue;
    const existing = latest.get(sale.discordUserId);
    if (!existing || expiresAt > existing.expiresAt) latest.set(sale.discordUserId, { sale, expiresAt });
  }
  return [...latest.values()];
}

function reminderStage(remainingDays) {
  if (remainingDays <= 0) return "expired";
  if (remainingDays <= 1) return "1";
  if (remainingDays <= 3) return "3";
  if (remainingDays <= 7) return "7";
  return "";
}

function brDate(date) {
  return new Intl.DateTimeFormat("pt-BR", {
    timeZone: "America/Sao_Paulo",
    day: "2-digit",
    month: "2-digit",
    year: "numeric"
  }).format(date);
}

async function sendReminder(client, sale, expiresAt, stage) {
  const user = await client.users.fetch(sale.discordUserId);
  const expired = stage === "expired";
  const title = expired ? "Seu acesso ao AlbionMKT venceu" : `Sua assinatura vence em ${stage} ${stage === "1" ? "dia" : "dias"}`;
  const description = expired
    ? "O cargo de assinante foi removido. Renove o plano para recuperar o programa, as atualizações e o suporte exclusivo."
    : "Renove antecipadamente para evitar a interrupção do acesso ao programa e aos canais exclusivos.";
  const lines = [
    description,
    "",
    `**Vencimento:** ${brDate(expiresAt)}`,
    `**Plano:** ${sale.planName || config.planName}`,
    config.paymentLink
      ? `**Renovar:** ${config.paymentLink}`
      : "Use `/pagar-pix` para mais 30 dias sem recorrencia ou `/assinar` para ativar a renovacao mensal."
  ];
  await user.send({
    embeds: [
      new EmbedBuilder()
        .setColor(expired ? 0xe74c3c : 0xc98247)
        .setTitle(title)
        .setDescription(lines.join("\n"))
        .setFooter({ text: "AlbionMKT • lembrete automático" })
        .setTimestamp()
    ]
  });
}

export async function processRenewalReminders(client, sendLog) {
  if (running || !client.isReady()) return;
  running = true;
  try {
    const state = await loadState();
    const current = Date.now();
    for (const { sale, expiresAt } of latestActiveSales(await listSales())) {
      const remainingDays = Math.ceil((expiresAt.getTime() - current) / DAY);
      const stage = reminderStage(remainingDays);
      if (!stage) continue;
      const periodKey = expiresAt.toISOString().slice(0, 10);
      const stateKey = `${sale.discordUserId}:${periodKey}:${stage}`;
      if (state[stateKey]) continue;

      let delivered = false;
      let deliveryError = "";
      if (stage === "expired") {
        await revokeRole(client, sale.discordUserId, "Período de acesso encerrado");
        await saveSale({
          sourceId: sale.sourceId,
          status: "expired",
          expiredAt: new Date().toISOString()
        });
        await publishSalesTable(client);
      }
      try {
        await sendReminder(client, sale, expiresAt, stage);
        delivered = true;
      } catch (error) {
        deliveryError = error.message;
      }

      state[stateKey] = {
        processedAt: new Date().toISOString(),
        delivered,
        sourceId: sale.sourceId
      };
      await saveState(state);
      await sendLog?.(stage === "expired" ? "Acesso expirado automaticamente" : "Lembrete de renovação enviado", [
        { name: "Usuário", value: `<@${sale.discordUserId}>`, inline: true },
        { name: "Vencimento", value: brDate(expiresAt), inline: true },
        { name: "Etapa", value: stage === "expired" ? "Expirado" : `${stage} dia(s)`, inline: true },
        { name: "Mensagem privada", value: delivered ? "Entregue" : `Falhou: ${deliveryError || "indisponível"}` }
      ], delivered ? 0x2ecc71 : 0xe67e22);
    }
  } finally {
    running = false;
  }
}
