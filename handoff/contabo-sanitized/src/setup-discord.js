import path from "node:path";
import { Client, GatewayIntentBits, PermissionFlagsBits } from "discord.js";
import { config, validateConfig } from "./config.js";
import { publishPanels } from "./panels.js";
import { CATEGORY_LAYOUT, CHANNEL_LAYOUT, SERVER_IDS } from "./server-layout.js";

validateConfig();

const client = new Client({ intents: [GatewayIntentBits.Guilds] });
const iconPath = path.resolve("assets", "albionmkt-icon-original.png");

function overwrite(id, allow = [], deny = []) {
  return { id, allow, deny };
}

function roleByName(roles, pattern) {
  return roles.find((role) => pattern.test(role.name));
}

async function clearInformationalChannel(channel) {
  if (!channel?.isTextBased() || !channel.messages || channel.isThread()) return 0;
  const messages = await channel.messages.fetch({ limit: 100 });
  if (!messages.size) return 0;
  const deleted = await channel.bulkDelete(messages, true);
  return deleted.size;
}

async function applyCategoryPermissions(category, audience, everyone, visitor, subscriber) {
  const commonPublic = {
    ViewChannel: true,
    ReadMessageHistory: true,
    UseApplicationCommands: true
  };
  await category.permissionOverwrites.edit(everyone, {
    ViewChannel: false,
    SendMessages: false
  });

  if (audience === "visitor") {
    await category.permissionOverwrites.edit(visitor, commonPublic);
    await category.permissionOverwrites.edit(subscriber, commonPublic);
  } else if (audience === "subscriber") {
    await category.permissionOverwrites.edit(subscriber, {
      ...commonPublic,
      SendMessagesInThreads: true
    });
  }
}

client.once("clientReady", async () => {
  try {
    const guild = await client.guilds.fetch(config.guildId);
    const me = await guild.members.fetchMe();
    const required = [
      PermissionFlagsBits.ManageChannels,
      PermissionFlagsBits.ManageRoles,
      PermissionFlagsBits.ManageMessages,
      PermissionFlagsBits.CreatePrivateThreads,
      PermissionFlagsBits.ManageThreads,
      PermissionFlagsBits.SendMessagesInThreads
    ];
    const missing = required.filter((permission) => !me.permissions.has(permission));
    if (missing.length) throw new Error("O bot ainda não recebeu todas as permissões técnicas necessárias.");

    let roles = await guild.roles.fetch();
    const everyone = guild.roles.everyone;
    const subscriber = config.subscriberRoleId
      ? await guild.roles.fetch(config.subscriberRoleId).catch(() => null)
      : roleByName(roles, /Assinante/i);
    if (!subscriber) throw new Error("Cargo de Assinante não encontrado.");

    let visitor = config.visitorRoleId
      ? await guild.roles.fetch(config.visitorRoleId).catch(() => null)
      : roleByName(roles, /Visitante/i);
    if (!visitor) {
      visitor = await guild.roles.create({
        name: config.visitorRoleName,
        hoist: false,
        mentionable: false,
        reason: "Acesso público após a introdução do AlbionMKT"
      });
      console.log(`Cargo criado: ${visitor.name} (${visitor.id})`);
      roles = await guild.roles.fetch();
    }

    const founder = roleByName(roles, /Fundador/i);
    const admin = roleByName(roles, /Admin/i);
    const botRole = me.roles.highest;
    // O Discord não permite que o bot recrie sobrescritas de cargos acima dele.
    // Fundadores e administradores com Administrador continuam ignorando bloqueios de canal.
    const editableStaffRoles = [founder, admin].filter((role) => role && role.position < botRole.position);
    const staffRoleIds = [...editableStaffRoles.map((role) => role.id), botRole.id];

    const audienceOverwrites = {
      visitor: [
        overwrite(everyone.id, [], [PermissionFlagsBits.ViewChannel, PermissionFlagsBits.SendMessages]),
        overwrite(visitor.id, [PermissionFlagsBits.ViewChannel, PermissionFlagsBits.ReadMessageHistory, PermissionFlagsBits.UseApplicationCommands]),
        overwrite(subscriber.id, [PermissionFlagsBits.ViewChannel, PermissionFlagsBits.ReadMessageHistory, PermissionFlagsBits.UseApplicationCommands]),
        ...staffRoleIds.map((id) => overwrite(id, [PermissionFlagsBits.ViewChannel, PermissionFlagsBits.ReadMessageHistory, PermissionFlagsBits.SendMessages, PermissionFlagsBits.ManageMessages]))
      ],
      subscriber: [
        overwrite(everyone.id, [], [PermissionFlagsBits.ViewChannel]),
        overwrite(subscriber.id, [PermissionFlagsBits.ViewChannel, PermissionFlagsBits.ReadMessageHistory, PermissionFlagsBits.UseApplicationCommands, PermissionFlagsBits.SendMessagesInThreads]),
        ...staffRoleIds.map((id) => overwrite(id, [PermissionFlagsBits.ViewChannel, PermissionFlagsBits.ReadMessageHistory, PermissionFlagsBits.SendMessages, PermissionFlagsBits.SendMessagesInThreads, PermissionFlagsBits.ManageThreads]))
      ],
      staff: [
        overwrite(everyone.id, [], [PermissionFlagsBits.ViewChannel]),
        ...staffRoleIds.map((id) => overwrite(id, [PermissionFlagsBits.ViewChannel, PermissionFlagsBits.ReadMessageHistory, PermissionFlagsBits.SendMessages, PermissionFlagsBits.Connect, PermissionFlagsBits.Speak, PermissionFlagsBits.ManageMessages]))
      ]
    };

    for (const item of CATEGORY_LAYOUT) {
      const category = await guild.channels.fetch(SERVER_IDS.categories[item.key]);
      if (!category) throw new Error(`Categoria não encontrada: ${item.key}`);
      if (category.name !== item.name) await category.setName(item.name);
      // Edite apenas os acessos essenciais. Isso preserva Fundador, Administração e
      // integrações existentes (como o Xenon) que o bot não deve remover.
      await applyCategoryPermissions(category, item.audience, everyone, visitor, subscriber);
      if (typeof item.position === "number") await category.setPosition(item.position);
      console.log(`Categoria organizada: ${item.name}`);
    }

    const cleanKeys = new Set(["entry", "resources", "faq", "sales", "start", "versions", "activation", "tutorials", "support", "commands"]);
    for (const item of CHANNEL_LAYOUT) {
      const channelId = SERVER_IDS.channels[item.key];
      const channel = await guild.channels.fetch(channelId);
      if (!channel) throw new Error(`Canal não encontrado: ${item.key}`);
      const parentId = item.parent ? SERVER_IDS.categories[item.parent] : null;
      if (!new Set(["entry", "staffVoice", "meetingVoice"]).has(item.key)) {
        if (channel.parentId !== parentId) await channel.setParent(parentId, { lockPermissions: false });
        if (channel.name !== item.name) await channel.setName(item.name);
        if (typeof item.position === "number") await channel.setPosition(item.position);
        if (item.topic && "setTopic" in channel && channel.topic !== item.topic) await channel.setTopic(item.topic);
      }
      if (cleanKeys.has(item.key)) {
        const deleted = await clearInformationalChannel(channel);
        if (deleted) console.log(`Mensagens antigas removidas de ${item.name}: ${deleted}`);
      }
      console.log(`Canal organizado: ${item.name}`);
    }

    const entry = await guild.channels.fetch(SERVER_IDS.channels.entry);

    const temporaryVoice = await guild.channels.fetch(SERVER_IDS.channels.temporaryVoice).catch(() => null);
    if (temporaryVoice) {
      await temporaryVoice.permissionOverwrites.edit(everyone, { ViewChannel: false }).catch(() => null);
      await temporaryVoice.permissionOverwrites.edit(visitor, { ViewChannel: true, Connect: true, Speak: true }).catch(() => null);
      await temporaryVoice.permissionOverwrites.edit(subscriber, { ViewChannel: true, Connect: true, Speak: true }).catch(() => null);
    }

    // O ícone do servidor é aplicado pela conta proprietária na interface do Discord.
    // Assim o bot não precisa receber a permissão ampla "Gerenciar servidor".
    await client.user.setAvatar(iconPath);

    const invite = await entry
      .createInvite({
        maxAge: 0,
        maxUses: 0,
        unique: false,
        reason: "Convite oficial para a entrada do AlbionMKT"
      })
      .catch(() => null);

    const panelIds = await publishPanels(client);
    console.log(`VISITOR_ROLE_ID=${visitor.id}`);
    console.log(`Convite oficial: ${invite?.url || "não criado (sem permissão)"}`);
    console.log(`Servidor organizado. Painéis publicados: ${panelIds.length}`);
  } finally {
    client.destroy();
  }
});

await client.login(config.discordToken);
