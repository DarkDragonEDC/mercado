import {
  PermissionFlagsBits,
  REST,
  Routes,
  SlashCommandBuilder
} from "discord.js";
import { config, validateConfig } from "./config.js";
import { COMMERCIAL_PLANS, formatPlanPrice } from "./commercial-plans.js";

validateConfig();

const commands = [
  new SlashCommandBuilder()
    .setName("assinar")
    .setDescription("Escolha e compre um plano oficial do AlbionMKT")
    .addStringOption((option) => option
      .setName("plano")
      .setDescription("Produto que deseja contratar por 30 dias")
      .setRequired(true)
      .addChoices(...COMMERCIAL_PLANS.map((plan) => ({ name: `${plan.name} — ${formatPlanPrice(plan)}`, value: plan.id }))))
    .addStringOption((option) =>
      option
        .setName("email")
        .setDescription("E-mail usado no Mercado Pago")
        .setRequired(true)
    ),
  new SlashCommandBuilder()
    .setName("pagar-pix")
    .setDescription("Gere um checkout individual com Pix para um plano oficial")
    .addStringOption((option) => option
      .setName("plano")
      .setDescription("Produto que deseja contratar por 30 dias")
      .setRequired(true)
      .addChoices(...COMMERCIAL_PLANS.map((plan) => ({ name: `${plan.name} — ${formatPlanPrice(plan)}`, value: plan.id }))))
    .addStringOption((option) =>
      option
        .setName("email")
        .setDescription("E-mail usado no Mercado Pago")
        .setRequired(true)
    ),
  new SlashCommandBuilder()
    .setName("teste-gratis")
    .setDescription(`Receba uma key gratis de ${config.freeTrialDays} dia, uma unica vez por usuario`),
  new SlashCommandBuilder()
    .setName("minha-assinatura")
    .setDescription("Consulte o estado da sua assinatura"),
  new SlashCommandBuilder()
    .setName("ajuda")
    .setDescription("Veja como utilizar o AlbionMKT e seus comandos"),
  new SlashCommandBuilder()
    .setName("status")
    .setDescription("Consulte o estado dos serviços do AlbionMKT"),
  new SlashCommandBuilder()
    .setName("suporte")
    .setDescription("Abra um atendimento privado com a equipe")
    .addStringOption((option) =>
      option
        .setName("assunto")
        .setDescription("Descreva brevemente o que você precisa")
        .setMaxLength(100)
        .setRequired(true)
    ),
  new SlashCommandBuilder()
    .setName("fechar-suporte")
    .setDescription("Encerre o atendimento privado atual"),
  new SlashCommandBuilder()
    .setName("publicar-paineis")
    .setDescription("Atualize os painéis oficiais do servidor")
    .setDefaultMemberPermissions(PermissionFlagsBits.ManageGuild),
  new SlashCommandBuilder()
    .setName("relatorio-vendas")
    .setDescription("Exporte o controle de vendas em CSV")
    .setDefaultMemberPermissions(PermissionFlagsBits.ManageGuild),
  new SlashCommandBuilder()
    .setName("estoque-keys")
    .setDescription("Consulte o painel de licencas")
    .setDefaultMemberPermissions(PermissionFlagsBits.ManageGuild),
  new SlashCommandBuilder()
    .setName("licenca-criar")
    .setDescription("Crie uma nova licenca do AlbionMKT")
    .addUserOption((option) => option.setName("cliente").setDescription("Cliente que recebera a key").setRequired(true))
    .addIntegerOption((option) => option.setName("dias").setDescription("Validade em dias").setMinValue(1).setMaxValue(3650).setRequired(true))
    .addStringOption((option) => option
      .setName("acesso")
      .setDescription("Funcionalidades liberadas por esta key")
      .setRequired(true)
      .addChoices(
        { name: "Compra", value: "purchase" },
        { name: "Venda", value: "sales" },
        { name: "Compra + Venda + Ciclo Automatico", value: "complete" }
      ))
    .addIntegerOption((option) => option.setName("computadores").setDescription("Quantidade de computadores").setMinValue(1).setMaxValue(10))
    .addStringOption((option) => option.setName("observacao").setDescription("Observacao interna").setMaxLength(300))
    .setDefaultMemberPermissions(PermissionFlagsBits.ManageGuild),
  new SlashCommandBuilder()
    .setName("licencas")
    .setDescription("Monitore licencas, vencimentos e computadores")
    .setDefaultMemberPermissions(PermissionFlagsBits.ManageGuild),
  new SlashCommandBuilder()
    .setName("licenca-info")
    .setDescription("Consulte uma licenca pelo ID ou key")
    .addStringOption((option) => option.setName("licenca").setDescription("ID, key completa ou identificador exibido").setRequired(true))
    .setDefaultMemberPermissions(PermissionFlagsBits.ManageGuild),
  new SlashCommandBuilder()
    .setName("licenca-entregar")
    .setDescription("Reenvie uma licenca por DM ao cliente vinculado")
    .addStringOption((option) => option.setName("licenca").setDescription("ID ou key completa").setRequired(true))
    .setDefaultMemberPermissions(PermissionFlagsBits.ManageGuild),
  new SlashCommandBuilder()
    .setName("licenca-estender")
    .setDescription("Adicione dias a uma licenca")
    .addStringOption((option) => option.setName("licenca").setDescription("ID ou key completa").setRequired(true))
    .addIntegerOption((option) => option.setName("dias").setDescription("Dias adicionais").setMinValue(1).setMaxValue(3650).setRequired(true))
    .setDefaultMemberPermissions(PermissionFlagsBits.ManageGuild),
  new SlashCommandBuilder()
    .setName("licenca-revogar")
    .setDescription("Bloqueie imediatamente uma licenca")
    .addStringOption((option) => option.setName("licenca").setDescription("ID ou key completa").setRequired(true))
    .addStringOption((option) => option.setName("motivo").setDescription("Motivo da revogacao").setMaxLength(300))
    .setDefaultMemberPermissions(PermissionFlagsBits.ManageGuild),
  new SlashCommandBuilder()
    .setName("licenca-reativar")
    .setDescription("Reative uma licenca revogada")
    .addStringOption((option) => option.setName("licenca").setDescription("ID ou key completa").setRequired(true))
    .addIntegerOption((option) => option.setName("dias").setDescription("Validade se ela ja expirou").setMinValue(1).setMaxValue(3650))
    .setDefaultMemberPermissions(PermissionFlagsBits.ManageGuild),
  new SlashCommandBuilder()
    .setName("licenca-resetar-pc")
    .setDescription("Libere os computadores vinculados a uma licenca")
    .addStringOption((option) => option.setName("licenca").setDescription("ID ou key completa").setRequired(true))
    .setDefaultMemberPermissions(PermissionFlagsBits.ManageGuild),
  new SlashCommandBuilder()
    .setName("licenca-modulos")
    .setDescription("Defina quais bots uma licenca pode utilizar")
    .addStringOption((option) => option.setName("licenca").setDescription("ID ou key completa").setRequired(true))
    .addStringOption((option) => option
      .setName("acesso")
      .setDescription("Novo acesso da licenca")
      .setRequired(true)
      .addChoices(
        { name: "Compra", value: "purchase" },
        { name: "Venda", value: "sales" },
        { name: "Compra + Venda + Ciclo Automatico", value: "complete" }
      ))
    .setDefaultMemberPermissions(PermissionFlagsBits.ManageGuild)
].map((command) => command.toJSON());

const rest = new REST({ version: "10" }).setToken(config.discordToken);
await rest.put(Routes.applicationGuildCommands(config.clientId, config.guildId), {
  body: commands
});
console.log("Comandos registrados no servidor.");
