const token = process.env.DISCORD_BOT_TOKEN?.trim();
const applicationId = process.env.DISCORD_APPLICATION_ID?.trim();
const guildId = process.env.DISCORD_GUILD_ID?.trim();

if (!token || !applicationId || !guildId) {
  throw new Error("DISCORD_BOT_TOKEN, DISCORD_APPLICATION_ID e DISCORD_GUILD_ID sao obrigatorios.");
}

const commands = [
  {
    name: "planos",
    description: "Mostra os planos e preços do AlbionMKT",
  },
  {
    name: "comprar",
    description: "Compra 30 dias de acesso ao AlbionMKT (pagamento único)",
    options: [{
      type: 3,
      name: "plano",
      description: "Plano desejado",
      required: true,
      choices: [
        { name: "Venda — R$ 39,90", value: "venda" },
        { name: "Compra — R$ 49,90", value: "compra" },
        { name: "Completo — R$ 99,90", value: "completo" },
      ],
    }],
  },
  {
    name: "meu_acesso",
    description: "Consulta sua licença e validade do AlbionMKT",
  },
  {
    name: "licenca_criar",
    description: "Cria uma nova licença do AlbionMKT",
    options: [
      { type: 6, name: "usuario", description: "Cliente que receberá a licença", required: true },
      { type: 4, name: "dias", description: "Validade em dias", min_value: 1, max_value: 3650 },
      { type: 4, name: "computadores", description: "Quantidade máxima de PCs", min_value: 1, max_value: 25 },
      {
        type: 3,
        name: "plano",
        description: "Módulos liberados",
        choices: [
          { name: "Compra + Venda", value: "completo" },
          { name: "Somente Compra", value: "compra" },
          { name: "Somente Venda", value: "venda" },
        ],
      },
    ],
  },
  {
    name: "licenca_listar",
    description: "Lista as licenças mais recentes",
    options: [{ type: 4, name: "limite", description: "Quantidade de resultados", min_value: 1, max_value: 20 }],
  },
  { name: "licenca_status", description: "Mostra os totais do sistema de licenças" },
  {
    name: "licenca_revogar",
    description: "Revoga uma licença pelo ID",
    options: [{ type: 3, name: "id", description: "ID completo da licença", required: true }],
  },
  {
    name: "licenca_resetar",
    description: "Remove os computadores vinculados à licença",
    options: [{ type: 3, name: "id", description: "ID completo da licença", required: true }],
  },
  {
    name: "licenca_prorrogar",
    description: "Prorroga uma licença pelo ID",
    options: [
      { type: 3, name: "id", description: "ID completo da licença", required: true },
      { type: 4, name: "dias", description: "Dias adicionais", required: true, min_value: 1, max_value: 3650 },
    ],
  },
];

const endpoint = `https://discord.com/api/v10/applications/${applicationId}/guilds/${guildId}/commands`;
const result = await fetch(endpoint, {
  method: "PUT",
  headers: {
    Authorization: `Bot ${token}`,
    "Content-Type": "application/json",
  },
  body: JSON.stringify(commands),
});
if (!result.ok) throw new Error(`Discord HTTP ${result.status}: ${await result.text()}`);
console.log(`DISCORD_COMMANDS_OK count=${(await result.json()).length}`);
