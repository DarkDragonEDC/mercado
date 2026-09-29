import { config } from "./config.js";

async function findRole(guild, roleId, roleName) {
  if (roleId) {
    const role = await guild.roles.fetch(roleId).catch(() => null);
    if (role) return role;
  }
  const roles = await guild.roles.fetch();
  const role = roles.find((item) => item.name === roleName);
  if (!role) throw new Error(`Cargo ${roleName} não encontrado no servidor.`);
  return role;
}

async function getSubscriberRole(guild) {
  return findRole(guild, config.subscriberRoleId, config.subscriberRoleName);
}

async function getVisitorRole(guild) {
  return findRole(guild, config.visitorRoleId, config.visitorRoleName);
}

export async function grantVisitorRole(client, discordUserId) {
  const guild = await client.guilds.fetch(config.guildId);
  const role = await getVisitorRole(guild);
  const member = await guild.members.fetch(discordUserId);
  if (!member.roles.cache.has(role.id)) {
    await member.roles.add(role.id, "Introdução do AlbionMKT concluída");
  }
  return role;
}

export async function grantRole(client, discordUserId) {
  const guild = await client.guilds.fetch(config.guildId);
  const role = await getSubscriberRole(guild);
  const member = await guild.members.fetch(discordUserId);
  if (!member.roles.cache.has(role.id)) {
    await member.roles.add(role.id, "Assinatura Mercado Pago ativa");
  }
}

export async function revokeRole(client, discordUserId, reason) {
  const guild = await client.guilds.fetch(config.guildId);
  const role = await getSubscriberRole(guild);
  const member = await guild.members.fetch(discordUserId).catch(() => null);
  if (member?.roles.cache.has(role.id)) {
    await member.roles.remove(role.id, reason);
  }
}
