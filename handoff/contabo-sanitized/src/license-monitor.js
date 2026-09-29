import { EmbedBuilder } from "discord.js";
import { config } from "./config.js";
import { formatLicenseModules, getLicenseStats, listLicenses } from "./license-store.js";

const PANEL_MARKER = "painel-licencas-albionmkt";
const BRAND_COLOR = 0xd4af37;

function brDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return new Intl.DateTimeFormat("pt-BR", {
    timeZone: "America/Sao_Paulo",
    dateStyle: "short",
    timeStyle: "short"
  }).format(date);
}

function statusLabel(status) {
  return {
    active: "Ativa",
    expired: "Expirada",
    revoked: "Revogada"
  }[status] || status;
}

function lastActivity(record) {
  const dates = record.devices
    .map((device) => new Date(device.lastSeenAt))
    .filter((date) => !Number.isNaN(date.getTime()));
  if (!dates.length) return "Ainda nao ativada";
  return brDate(new Date(Math.max(...dates)));
}

export async function publishLicenseMonitor(client) {
  if (!config.licenseMonitorChannelId || !client.isReady()) return null;
  const channel = await client.channels.fetch(config.licenseMonitorChannelId);
  if (!channel?.isTextBased()) throw new Error("Canal de monitoramento de licencas invalido.");

  const [records, stats] = await Promise.all([listLicenses(), getLicenseStats()]);
  const displayed = records.slice(0, 10);
  const embed = new EmbedBuilder()
    .setColor(BRAND_COLOR)
    .setTitle("Controle de licencas do AlbionMKT")
    .setDescription([
      `Ativas **${stats.active}** | Expiram em 7 dias **${stats.expiring}** | Expiradas **${stats.expired}** | Revogadas **${stats.revoked}**`,
      `Computadores vinculados **${stats.devices}** | Total **${stats.total}**`,
      "As keys aparecem parcialmente ocultas por seguranca."
    ].join("\n"))
    .setFooter({ text: PANEL_MARKER })
    .setTimestamp();

  if (!displayed.length) {
    embed.addFields({ name: "Nenhuma licenca", value: "As novas licencas aparecerao automaticamente aqui." });
  } else {
    for (const record of displayed) {
      embed.addFields({
        name: `${statusLabel(record.effectiveStatus)} - ${record.keyPrefix}`.slice(0, 256),
        value: [
          `Cliente: ${record.discordUserId ? `<@${record.discordUserId}> (\`${record.discordUserId}\`)` : "Nao vinculado"}`,
          `Criada: **${brDate(record.createdAt)}** | Vence: **${brDate(record.expiresAt)}**`,
          `Acesso: **${formatLicenseModules(record.modules)}** (\`${(record.modules || ["purchase_orders"]).join(", ")}\`)`,
          `Computadores: **${record.devices.length}/${record.maxDevices}** | Ultima atividade: **${lastActivity(record)}**`,
          `ID: \`${record.id}\``
        ].join("\n")
      });
    }
  }

  const messages = await channel.messages.fetch({ limit: 50 });
  const existing = messages.find((message) =>
    message.author.id === client.user.id &&
    message.embeds.some((item) => item.footer?.text === PANEL_MARKER)
  );
  if (existing) return existing.edit({ embeds: [embed] });
  return channel.send({ embeds: [embed] });
}
