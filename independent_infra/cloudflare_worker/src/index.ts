import { handleDiscordInteraction } from "./discord";
import {
  processMercadoPagoPayment,
  removeExpiredRoles,
  verifyMercadoPagoWebhook,
} from "./commercial";
import {
  activateLicense,
  createLicense,
  extendLicense,
  licenseStats,
  listLicenses,
  parseCreateInput,
  parseLicenseRequest,
  resetLicenseDevices,
  revokeLicense,
  validateLicense,
} from "./licensing";
import { safeSecretMatches } from "./security";
import type { Env } from "./types";

const MAX_BODY_BYTES = 8 * 1024;
const MAX_REQUESTS_PER_MINUTE = 60;
const UUID_PATTERN = /^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/i;

const rateBuckets = new Map<string, { minute: number; count: number }>();

function json(body: unknown, status = 200): Response {
  return Response.json(body, {
    status,
    headers: {
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
      "Referrer-Policy": "no-referrer",
    },
  });
}

function allowRequest(request: Request): boolean {
  const minute = Math.floor(Date.now() / 60_000);
  const identity = request.headers.get("CF-Connecting-IP") ?? "unknown";
  const current = rateBuckets.get(identity);
  if (!current || current.minute !== minute) {
    if (rateBuckets.size > 5_000) rateBuckets.clear();
    rateBuckets.set(identity, { minute, count: 1 });
    return true;
  }
  current.count += 1;
  return current.count <= MAX_REQUESTS_PER_MINUTE;
}

async function readJson(request: Request): Promise<unknown> {
  const declared = Number(request.headers.get("Content-Length") ?? "0");
  if (declared > MAX_BODY_BYTES) throw new Error("BODY_TOO_LARGE");
  const body = await request.text();
  if (new TextEncoder().encode(body).byteLength > MAX_BODY_BYTES) {
    throw new Error("BODY_TOO_LARGE");
  }
  return JSON.parse(body);
}

async function isAdmin(request: Request, env: Env): Promise<boolean> {
  const header = request.headers.get("Authorization") ?? "";
  if (!header.startsWith("Bearer ")) return false;
  return safeSecretMatches(header.slice(7), env.ALBIONMKT_ADMIN_TOKEN);
}

function idFromPath(pathname: string, suffix: string): string | null {
  const prefix = "/api/admin/licenses/";
  if (!pathname.startsWith(prefix) || !pathname.endsWith(suffix)) return null;
  const id = pathname.slice(prefix.length, pathname.length - suffix.length);
  return UUID_PATTERN.test(id) ? id : null;
}

async function handleLicenseProtocol(request: Request, env: Env, action: "activate" | "validate"): Promise<Response> {
  if (!allowRequest(request)) {
    return json(
      { valid: false, code: "RATE_LIMIT", message: "Muitas tentativas. Aguarde um momento." },
      429,
    );
  }
  const payload = parseLicenseRequest(await readJson(request));
  if (!payload) {
    return json({ valid: false, code: "INVALID_REQUEST", message: "Solicitação inválida." }, 400);
  }
  const result = action === "activate"
    ? await activateLicense(env, payload)
    : await validateLicense(env, payload);
  return json(result.body, result.status);
}

async function handleAdmin(request: Request, env: Env, url: URL): Promise<Response> {
  if (!(await isAdmin(request, env))) {
    return json({ detail: "credencial administrativa invalida" }, 401);
  }
  if (request.method === "POST" && url.pathname === "/api/admin/licenses") {
    const input = parseCreateInput(await readJson(request));
    return input
      ? json(await createLicense(env, input))
      : json({ detail: "dados da licenca invalidos" }, 400);
  }
  if (request.method === "GET" && url.pathname === "/api/admin/licenses") {
    const limit = Number(url.searchParams.get("limit") ?? 50);
    const discordUserId = url.searchParams.get("discord_user_id") ?? undefined;
    return json(await listLicenses(env, Number.isFinite(limit) ? limit : 50, discordUserId));
  }
  if (request.method === "GET" && url.pathname === "/api/admin/stats") {
    return json(await licenseStats(env));
  }

  const revokeId = idFromPath(url.pathname, "/revoke");
  if (request.method === "POST" && revokeId) {
    return (await revokeLicense(env, revokeId))
      ? json({ ok: true })
      : json({ detail: "licenca nao encontrada ou ja revogada" }, 404);
  }
  const resetId = idFromPath(url.pathname, "/reset-devices");
  if (request.method === "POST" && resetId) {
    return (await resetLicenseDevices(env, resetId))
      ? json({ ok: true })
      : json({ detail: "licenca nao encontrada" }, 404);
  }
  const extendId = idFromPath(url.pathname, "/extend");
  if (request.method === "POST" && extendId) {
    const payload = await readJson(request) as { days?: unknown };
    const expiration = await extendLicense(env, extendId, Number(payload?.days));
    return expiration
      ? json({ ok: true, expires_at: expiration })
      : json({ detail: "licenca nao encontrada ou dias invalidos" }, 404);
  }
  return json({ detail: "endpoint administrativo nao encontrado" }, 404);
}

async function handleMercadoPagoWebhook(
  request: Request,
  env: Env,
  url: URL,
  context?: ExecutionContext,
): Promise<Response> {
  const dataId = url.searchParams.get("data.id") ?? "";
  const valid = await verifyMercadoPagoWebhook(
    env,
    request.headers.get("x-signature") ?? "",
    request.headers.get("x-request-id") ?? "",
    dataId,
  );
  if (!valid) return json({ detail: "assinatura de webhook invalida" }, 401);
  const payload = await readJson(request) as { type?: unknown; data?: { id?: unknown } };
  if (payload.type !== "payment" || String(payload.data?.id ?? "") !== dataId) {
    return json({ detail: "notificacao ignorada" }, 202);
  }
  const processing = processMercadoPagoPayment(env, dataId);
  if (context) context.waitUntil(processing);
  else await processing;
  return json({ received: true });
}

function paymentPage(state: string): Response {
  const messages: Record<string, string> = {
    aprovado: "Pagamento recebido. A confirmação e a licença serão enviadas pelo bot no Discord.",
    pendente: "Pagamento pendente. O bot fará a entrega automaticamente após a aprovação.",
    falhou: "O pagamento não foi concluído. Volte ao Discord e crie um novo pedido quando desejar.",
  };
  const message = messages[state];
  if (!message) return new Response("Nao encontrado", { status: 404 });
  return new Response(
    `<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>AlbionMKT</title><body style="font:16px system-ui;background:#111827;color:#f9fafb;max-width:680px;margin:15vh auto;padding:32px"><h1>AlbionMKT</h1><p>${message}</p><p>Você já pode fechar esta página.</p></body></html>`,
    { headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" } },
  );
}

export default {
  async fetch(request: Request, env: Env, context?: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    try {
      if (request.method === "GET" && url.pathname === "/health") {
        return json({ status: "ok", service: "albionmkt-license" });
      }
      if (request.method === "POST" && url.pathname === "/discord/interactions") {
        return handleDiscordInteraction(request, env);
      }
      if (request.method === "POST" && url.pathname === "/webhooks/mercadopago") {
        return handleMercadoPagoWebhook(request, env, url, context);
      }
      if (request.method === "GET" && url.pathname.startsWith("/pagamento/")) {
        return paymentPage(url.pathname.slice("/pagamento/".length));
      }
      if (request.method === "POST" && url.pathname === "/api/licenses/activate") {
        return handleLicenseProtocol(request, env, "activate");
      }
      if (request.method === "POST" && url.pathname === "/api/licenses/validate") {
        return handleLicenseProtocol(request, env, "validate");
      }
      if (url.pathname.startsWith("/api/admin/")) {
        return handleAdmin(request, env, url);
      }
      return json({ detail: "nao encontrado" }, 404);
    } catch (caught) {
      if (caught instanceof Error && caught.message === "BODY_TOO_LARGE") {
        return json({ detail: "corpo muito grande" }, 413);
      }
      if (caught instanceof SyntaxError) return json({ detail: "json invalido" }, 400);
      return json({ detail: "falha temporaria" }, 500);
    }
  },
  async scheduled(_controller: ScheduledController, env: Env, context: ExecutionContext): Promise<void> {
    context.waitUntil(removeExpiredRoles(env));
  },
};
