import { env } from "cloudflare:workers";
import { beforeEach, describe, expect, it } from "vitest";
import worker from "../src/index";
import type { Env } from "../src/types";

const ADMIN_TOKEN = "test-admin-token-000000000000000000000000";
const HWID_A = "a".repeat(64);
const HWID_B = "b".repeat(64);

async function call(
  path: string,
  options: { method?: string; body?: unknown; admin?: boolean } = {},
): Promise<Response> {
  const headers: Record<string, string> = {};
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (options.admin) headers.Authorization = `Bearer ${ADMIN_TOKEN}`;
  return worker.fetch(
    new Request(`https://license.test${path}`, {
      method: options.method ?? "GET",
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    }),
    env as unknown as Env,
  );
}

async function createLicense(overrides: Record<string, unknown> = {}): Promise<Record<string, unknown>> {
  const response = await call("/api/admin/licenses", {
    method: "POST",
    admin: true,
    body: {
      discord_user_id: "1366066241667862680",
      duration_days: 30,
      device_limit: 1,
      modules: ["purchase_orders", "sales_orders"],
      ...overrides,
    },
  });
  expect(response.status).toBe(200);
  return response.json<Record<string, unknown>>();
}

function licenseBody(key: unknown, hwid = HWID_A): Record<string, unknown> {
  return { key, hwid, appVersion: "2.7.2" };
}

describe("API independente do AlbionMKT", () => {
  beforeEach(async () => {
    const database = (env as Cloudflare.Env).DB;
    await database.batch([
      database.prepare("DELETE FROM commercial_orders"),
      database.prepare("DELETE FROM license_devices"),
      database.prepare("DELETE FROM licenses"),
    ]);
  });

  it("expõe somente o health check público e protege a administração", async () => {
    const health = await call("/health");
    expect(health.status).toBe(200);
    expect(await health.json()).toEqual({ status: "ok", service: "albionmkt-license" });
    expect((await call("/api/admin/stats")).status).toBe(401);
    expect((await call("/api/admin/stats", { admin: true })).status).toBe(200);
  });

  it("executa ativação, validação e limite de dispositivo sem expor a key em listagens", async () => {
    const created = await createLicense();
    const key = created.key;
    expect(key).toMatch(/^ALBIONMKT-/);

    const notActivated = await call("/api/licenses/validate", {
      method: "POST",
      body: licenseBody(key),
    });
    expect(notActivated.status).toBe(403);
    expect((await notActivated.json<{ code: string }>()).code).toBe("NOT_ACTIVATED");

    const activated = await call("/api/licenses/activate", {
      method: "POST",
      body: licenseBody(key),
    });
    expect(activated.status).toBe(200);
    expect((await activated.json<{ newlyActivated: boolean }>()).newlyActivated).toBe(true);

    const repeated = await call("/api/licenses/activate", {
      method: "POST",
      body: licenseBody(key),
    });
    expect((await repeated.json<{ newlyActivated: boolean }>()).newlyActivated).toBe(false);

    const secondDevice = await call("/api/licenses/activate", {
      method: "POST",
      body: licenseBody(key, HWID_B),
    });
    expect(secondDevice.status).toBe(403);
    expect((await secondDevice.json<{ code: string }>()).code).toBe("DEVICE_LIMIT");

    const listed = await call("/api/admin/licenses", { admin: true });
    const listedText = await listed.text();
    expect(listedText).not.toContain(String(key));
    expect(JSON.parse(listedText)[0].device_count).toBe(1);
  });

  it("reseta computadores, prorroga e revoga a licença", async () => {
    const created = await createLicense();
    const key = created.key;
    const id = String(created.id);
    await call("/api/licenses/activate", { method: "POST", body: licenseBody(key) });

    expect((await call(`/api/admin/licenses/${id}/reset-devices`, { method: "POST", admin: true })).status).toBe(200);
    expect((await call("/api/licenses/activate", { method: "POST", body: licenseBody(key, HWID_B) })).status).toBe(200);
    expect((await call(`/api/admin/licenses/${id}/extend`, { method: "POST", admin: true, body: { days: 5 } })).status).toBe(200);
    expect((await call(`/api/admin/licenses/${id}/revoke`, { method: "POST", admin: true })).status).toBe(200);

    const rejected = await call("/api/licenses/validate", { method: "POST", body: licenseBody(key, HWID_B) });
    expect(rejected.status).toBe(403);
    expect((await rejected.json<{ code: string }>()).code).toBe("REVOKED");
  });

  it("recusa formatos inválidos antes de consultar o banco", async () => {
    const bad = await call("/api/licenses/activate", {
      method: "POST",
      body: licenseBody("key-curta"),
    });
    expect(bad.status).toBe(400);
    expect((await bad.json<{ code: string }>()).code).toBe("INVALID_REQUEST");
  });
});
