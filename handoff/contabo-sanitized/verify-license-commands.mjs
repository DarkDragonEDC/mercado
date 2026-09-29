import "dotenv/config";
import assert from "node:assert/strict";

const url = `https://discord.com/api/v10/applications/${process.env.DISCORD_CLIENT_ID}/guilds/${process.env.DISCORD_GUILD_ID}/commands`;
const response = await fetch(url, {
  headers: { Authorization: `Bot ${process.env.DISCORD_TOKEN}` }
});
const commands = await response.json();
if (!response.ok) throw new Error(`Discord ${response.status}`);

const expectedChoices = new Set(["purchase", "sales", "complete"]);
for (const commandName of ["licenca-criar", "licenca-modulos"]) {
  const command = commands.find((item) => item.name === commandName);
  assert.ok(command, `Comando ausente: ${commandName}`);
  const access = command.options?.find((item) => item.name === "acesso");
  assert.ok(access?.required, `Opcao acesso obrigatoria ausente em ${commandName}`);
  assert.deepEqual(new Set(access.choices?.map((item) => item.value)), expectedChoices);
}

console.log("LICENSE_COMMANDS_TEST=OK");
