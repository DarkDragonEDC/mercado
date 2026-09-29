import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";
import { AttachmentBuilder, EmbedBuilder } from "discord.js";
import { config } from "./config.js";

const dataDir = path.resolve("data");
const dataFile = path.join(dataDir, "sales.json");
const PANEL_MARKER = "controle-vendas-albionmkt";
const BRAND_COLOR = 0xd4af37;
let queue = Promise.resolve();

async function loadAll() {
  try {
    return JSON.parse(await readFile(dataFile, "utf8"));
  } catch (error) {
    if (error.code === "ENOENT") return {};
    throw error;
  }
}

async function saveAll(data) {
  await mkdir(dataDir, { recursive: true });
  const temporary = `${dataFile}.tmp`;
  await writeFile(temporary, JSON.stringify(data, null, 2), "utf8");
  await rename(temporary, dataFile);
}

function serialized(operation) {
  const result = queue.then(operation, operation);
  queue = result.catch(() => {});
  return result;
}

function maskedLicenseKey(value) {
  const text = String(value || "").trim();
  if (!text) return "";
  if (text.includes("...") || text.length < 20) return text;
  return `${text.slice(0, 14)}...${text.slice(-5)}`;
}

export function saveSale(record) {
  return serialized(async () => {
    const all = await loadAll();
    const existing = all[record.sourceId] || {};
    all[record.sourceId] = {
      ...existing,
      ...record,
      licenseKey: record.licenseKey ? maskedLicenseKey(record.licenseKey) : (existing.licenseKey || "-"),
      updatedAt: new Date().toISOString()
    };
    await saveAll(all);
    return all[record.sourceId];
  });
}

export async function listSales() {
  const all = await loadAll();
  return Object.values(all).sort((a, b) =>
    new Date(b.paidAt || b.updatedAt) - new Date(a.paidAt || a.updatedAt)
  );
}

function short(value, length) {
  const text = String(value || "-").replace(/[\r\n|`]/g, " ").trim();
  return text.length > length ? `${text.slice(0, length - 1)}…` : text;
}

function pad(value, length) {
  return short(value, length).padEnd(length, " ");
}

function brDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "-" : new Intl.DateTimeFormat("pt-BR", {
    timeZone: "America/Sao_Paulo",
    day: "2-digit",
    month: "2-digit",
    year: "2-digit"
  }).format(date);
}

function money(record) {
  return `R$ ${Number(record.amount || 0).toFixed(2).replace(".", ",")}`;
}

function expirationDate(record) {
  const explicit = new Date(record.expiresAt || "");
  if (!Number.isNaN(explicit.getTime())) return brDate(explicit);
  const paidAt = new Date(record.paidAt || record.updatedAt);
  if (Number.isNaN(paidAt.getTime())) return "-";
  paidAt.setUTCDate(paidAt.getUTCDate() + config.accessDays);
  return brDate(paidAt);
}

function statusLabel(status) {
  const labels = {
    approved: "Aprovado",
    authorized: "Autorizado",
    pending: "Pendente",
    cancelled: "Cancelado",
    rejected: "Recusado",
    refunded: "Reembolsado",
    expired: "Expirado"
  };
  return labels[String(status || "").toLowerCase()] || String(status || "-");
}

export async function publishSalesTable(client) {
  if (!config.salesControlChannelId) return null;
  const channel = await client.channels.fetch(config.salesControlChannelId);
  if (!channel?.isTextBased()) throw new Error("Canal de controle de vendas invalido.");

  const sales = await listSales();
  const approved = sales.filter((sale) => ["approved", "authorized"].includes(sale.status));
  const total = approved.reduce((sum, sale) => sum + Number(sale.amount || 0), 0);
  const rows = sales.slice(0, 15).map((sale) =>
    `${pad(sale.username || sale.discordUserId, 14)} ${pad(brDate(sale.paidAt), 8)} ${pad(expirationDate(sale), 8)} ${pad(sale.planName, 12)} ${pad(money(sale), 9)} ${pad(sale.licenseKey || "-", 31)} ${pad(statusLabel(sale.status), 11)}`
  );
  const table = [
    `${pad("Cliente", 14)} ${pad("Compra", 8)} ${pad("Expira", 8)} ${pad("Plano", 12)} ${pad("Valor", 9)} ${pad("Key", 31)} ${pad("Situação", 11)}`,
    "-".repeat(110),
    ...(rows.length ? rows : ["Nenhuma venda registrada."])
  ].join("\n");

  const embed = new EmbedBuilder()
    .setColor(BRAND_COLOR)
    .setTitle("📊 Controle de vendas do AlbionMKT")
    .setDescription(`\`\`\`text\n${table}\n\`\`\``)
    .addFields(
      { name: "Vendas aprovadas", value: String(approved.length), inline: true },
      { name: "Total registrado", value: `R$ ${total.toFixed(2).replace(".", ",")}`, inline: true },
      { name: "Exibição", value: `Últimos ${Math.min(sales.length, 15)} registros`, inline: true }
    )
    .setFooter({ text: PANEL_MARKER })
    .setTimestamp();

  const messages = await channel.messages.fetch({ limit: 50 });
  const existing = messages.find((message) =>
    message.author.id === client.user.id &&
    message.embeds.some((item) => item.footer?.text === PANEL_MARKER)
  );
  if (existing) return existing.edit({ embeds: [embed] });
  return channel.send({ embeds: [embed] });
}

function csvCell(value) {
  let text = String(value ?? "").replace(/\r?\n/g, " ");
  if (/^[=+\-@]/.test(text)) text = `'${text}`;
  return `"${text.replace(/"/g, '""')}"`;
}

export async function createSalesCsvAttachment() {
  const sales = await listSales();
  const header = ["Cliente", "Discord ID", "Data", "Vencimento", "Plano", "Valor", "Moeda", "Key", "Situação", "Pagamento", "Mensagem privada", "Entrega do executável"].map(csvCell);
  const rows = sales.map((sale) => [
    sale.username,
    sale.discordUserId,
    sale.paidAt,
    expirationDate(sale),
    sale.planName,
    sale.amount,
    sale.currency,
    sale.licenseKey,
    statusLabel(sale.status),
    sale.paymentId || sale.sourceId,
    sale.dmDelivered === true ? "Entregue" : sale.dmDelivered === false ? "Falhou/bloqueada" : "Não informado",
    sale.executableDelivery || "Não informado"
  ].map(csvCell));
  const csv = `\uFEFF${[header, ...rows].map((row) => row.join(";")).join("\r\n")}`;
  return new AttachmentBuilder(Buffer.from(csv, "utf8"), {
    name: `vendas-albionmkt-${new Date().toISOString().slice(0, 10)}.csv`
  });
}

export async function registerSale(client, record) {
  let username = record.username;
  if (!username && record.discordUserId) {
    const user = await client.users.fetch(record.discordUserId).catch(() => null);
    username = user?.globalName || user?.username || record.discordUserId;
  }
  const paidAt = record.paidAt || new Date().toISOString();
  const expiresAt = record.expiresAt || new Date(new Date(paidAt).getTime() + config.accessDays * 86_400_000).toISOString();
  const saved = await saveSale({
    ...record,
    username: username || record.discordUserId,
    planName: record.planName || config.planName,
    currency: record.currency || config.currency,
    licenseKey: record.licenseKey,
    paidAt,
    expiresAt
  });
  await publishSalesTable(client);
  return saved;
}
