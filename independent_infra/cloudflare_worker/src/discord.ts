import {
  createLicense,
  extendLicense,
  licenseStats,
  listLicenses,
  parseCreateInput,
  resetLicenseDevices,
  revokeLicense,
} from "./licensing";
import {
  COMMERCIAL_PLANS,
  createCheckout,
  formatPrice,
  isCommercialPlanId,
  latestUserAccess,
} from "./commercial";
import { verifyDiscordSignature } from "./security";
import type { Env, ModuleId } from "./types";

interface DiscordOption {
  name: string;
  value?: string | number;
}

interface DiscordInteraction {
  type: number;
  guild_id?: string;
  member?: {
    permissions?: string;
    user?: { id?: string };
  };
  data?: {
    name?: string;
    options?: DiscordOption[];
  };
}

const PERMISSION_ADMINISTRATOR = 1n << 3n;
const PERMISSION_MANAGE_GUILD = 1n << 5n;

function response(
  content: string,
  status = 200,
  components?: Array<Record<string, unknown>>,
): Response {
  return Response.json(
    {
      type: 4,
      data: {
        content: content.slice(0, 1950),
        flags: 64,
        allowed_mentions: { parse: [] },
        ...(components ? { components } : {}),
      },
    },
    { status },
  );
}

function option(interaction: DiscordInteraction, name: string): string | number | undefined {
  return interaction.data?.options?.find((item) => item.name === name)?.value;
}

function hasAdminPermission(interaction: DiscordInteraction, env: Env): boolean {
  if (!interaction.guild_id || !env.DISCORD_GUILD_ID || interaction.guild_id !== env.DISCORD_GUILD_ID) {
    return false;
  }
  const userId = interaction.member?.user?.id ?? "";
  const explicitAdmins = new Set(
    (env.DISCORD_ADMIN_USER_IDS ?? "")
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean),
  );
  // Quando a lista está configurada, ela é a autoridade exclusiva. Assim,
  // nenhum futuro cargo administrativo amplia sozinho o acesso a licenças.
  if (explicitAdmins.size > 0) return explicitAdmins.has(userId);
  try {
    const permissions = BigInt(interaction.member?.permissions ?? "0");
    return Boolean(
      permissions & PERMISSION_ADMINISTRATOR || permissions & PERMISSION_MANAGE_GUILD,
    );
  } catch {
    return false;
  }
}

function moduleIds(plan: string): ModuleId[] {
  if (plan === "compra") return ["purchase_orders"];
  if (plan === "venda") return ["sales_orders"];
  return ["purchase_orders", "sales_orders"];
}

async function runCommand(interaction: DiscordInteraction, env: Env): Promise<Response> {
  if (!interaction.guild_id || interaction.guild_id !== env.DISCORD_GUILD_ID) {
    return response("Este bot funciona somente no servidor oficial do AlbionMKT.");
  }
  const command = interaction.data?.name;
  const userId = interaction.member?.user?.id ?? "";

  if (command === "planos") {
    return response(
      "**Acesso AlbionMKT por 30 dias**\n" +
        `Venda: **${formatPrice(COMMERCIAL_PLANS.venda.amountCents)}**\n` +
        `Compra: **${formatPrice(COMMERCIAL_PLANS.compra.amountCents)}**\n` +
        `Completo: **${formatPrice(COMMERCIAL_PLANS.completo.amountCents)}**\n\n` +
        "Pagamento único, sem assinatura ou renovação automática. Use `/comprar` para continuar.",
    );
  }

  if (command === "comprar") {
    const planId = option(interaction, "plano");
    if (!userId || !isCommercialPlanId(planId)) return response("Escolha um plano válido.");
    const checkout = await createCheckout(env, userId, interaction.guild_id, planId);
    const plan = COMMERCIAL_PLANS[planId];
    return response(
      `Pedido criado: **${plan.name}**, 30 dias por **${formatPrice(plan.amountCents)}**.\n` +
        "Depois da aprovação, o cargo e a licença serão entregues automaticamente. Não existe renovação automática.",
      200,
      [{
        type: 1,
        components: [{ type: 2, style: 5, label: "Pagar com Mercado Pago", url: checkout.checkoutUrl }],
      }],
    );
  }

  if (command === "meu_acesso") {
    if (!userId) return response("Não foi possível identificar sua conta.");
    const access = await latestUserAccess(env, userId);
    if (!access) return response("Você ainda não possui um acesso aprovado.");
    const plan = COMMERCIAL_PLANS[access.order.plan_id];
    const expired = !access.order.access_expires_at || access.order.access_expires_at <= new Date().toISOString();
    return response(
      `**${plan.name}** — ${expired ? "expirado" : "ativo"}\n` +
        `Validade: \`${access.order.access_expires_at}\`\n` +
        `Chave: \`${access.key}\`\n` +
        (env.ALBIONMKT_DOWNLOAD_URL ? `Download oficial: ${env.ALBIONMKT_DOWNLOAD_URL}` : ""),
    );
  }

  if (!hasAdminPermission(interaction, env)) {
    return response("Você não possui permissão para administrar licenças.");
  }
  if (command === "licenca_criar") {
    const usuario = String(option(interaction, "usuario") ?? "");
    const dias = Number(option(interaction, "dias") ?? 30);
    const computadores = Number(option(interaction, "computadores") ?? 1);
    const plano = String(option(interaction, "plano") ?? "completo");
    const input = parseCreateInput({
      discord_user_id: usuario,
      duration_days: dias,
      device_limit: computadores,
      modules: moduleIds(plano),
      notes: `Criada pelo Discord por ${interaction.member?.user?.id ?? "desconhecido"}`,
    });
    if (!input) return response("Parâmetros inválidos para criar a licença.");
    const created = await createLicense(env, input);
    return response(
      "Licença criada. A key completa aparece somente nesta resposta:\n" +
        `\`${created.key}\`\n` +
        `ID: \`${created.id}\`\n` +
        `Vence: \`${created.expires_at}\``,
    );
  }

  if (command === "licenca_status") {
    const stats = await licenseStats(env);
    return response(
      "**Controle independente de licenças**\n" +
        `Ativas: **${stats.active}**\n` +
        `Expiram em 7 dias: **${stats.expires_within_7_days}**\n` +
        `Expiradas: **${stats.expired}**\n` +
        `Revogadas: **${stats.revoked}**\n` +
        `Computadores: **${stats.devices}**\n` +
        `Total: **${stats.total}**`,
    );
  }

  if (command === "licenca_listar") {
    const limite = Math.max(1, Math.min(20, Number(option(interaction, "limite") ?? 10)));
    const licenses = await listLicenses(env, limite);
    if (!licenses.length) return response("Nenhuma licença cadastrada.");
    const lines = licenses.map(
      (item) =>
        `\`${String(item.id).slice(0, 8)}\` ${item.key_preview} — ` +
        `${item.revoked_at ? "revogada" : "ativa/expiração controlada"} — ` +
        `${item.device_count}/${item.device_limit} PCs`,
    );
    return response(lines.join("\n"));
  }

  const id = String(option(interaction, "id") ?? "");
  if (!/^[a-f0-9-]{36}$/i.test(id)) return response("Informe o ID completo da licença.");

  if (command === "licenca_revogar") {
    return response(
      (await revokeLicense(env, id))
        ? `Licença \`${id}\` revogada.`
        : "Licença não encontrada ou já revogada.",
    );
  }
  if (command === "licenca_resetar") {
    return response(
      (await resetLicenseDevices(env, id))
        ? `Computadores da licença \`${id}\` removidos.`
        : "Licença não encontrada.",
    );
  }
  if (command === "licenca_prorrogar") {
    const dias = Number(option(interaction, "dias") ?? 0);
    const expiration = await extendLicense(env, id, dias);
    return response(
      expiration
        ? `Licença \`${id}\` prorrogada até \`${expiration}\`.`
        : "Licença não encontrada ou quantidade de dias inválida.",
    );
  }
  return response("Comando de licença não reconhecido.");
}

export async function handleDiscordInteraction(request: Request, env: Env): Promise<Response> {
  const signature = request.headers.get("X-Signature-Ed25519") ?? "";
  const timestamp = request.headers.get("X-Signature-Timestamp") ?? "";
  const publicKey = env.DISCORD_PUBLIC_KEY ?? "";
  const body = await request.text();
  if (!(await verifyDiscordSignature(publicKey, signature, timestamp, body))) {
    return new Response("assinatura invalida", { status: 401 });
  }
  let interaction: DiscordInteraction;
  try {
    interaction = JSON.parse(body) as DiscordInteraction;
  } catch {
    return new Response("json invalido", { status: 400 });
  }
  if (interaction.type === 1) return Response.json({ type: 1 });
  if (interaction.type !== 2) return response("Interação não suportada.");
  try {
    return await runCommand(interaction, env);
  } catch {
    return response("Falha temporária ao executar o comando. Tente novamente.");
  }
}
