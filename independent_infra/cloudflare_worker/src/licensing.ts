import {
  generateLicenseKey,
  hwidDigest,
  licenseDigest,
  maskedKey,
  normalizeKey,
  validateHwid,
  validateKey,
  validateVersion,
} from "./security";
import type {
  CreateLicenseInput,
  Env,
  LicenseRequest,
  LicenseRow,
  ModuleId,
} from "./types";

export interface ProtocolResult {
  status: number;
  body: Record<string, unknown>;
}

function utcNow(): string {
  return new Date().toISOString();
}

function error(code: string, message: string, status = 403): ProtocolResult {
  return { status, body: { valid: false, code, message } };
}

function parseModules(value: string): ModuleId[] {
  const parsed: unknown = JSON.parse(value);
  if (!Array.isArray(parsed)) return [];
  return parsed.filter(
    (module): module is ModuleId =>
      module === "purchase_orders" || module === "sales_orders",
  );
}

function checkLicense(row: LicenseRow | null, now = utcNow()): ProtocolResult | null {
  if (!row) return error("INVALID_KEY", "Key invalida.", 404);
  if (row.revoked_at) return error("REVOKED", "Esta licenca foi revogada.");
  if (row.expires_at <= now) return error("EXPIRED", "Esta licenca esta expirada.");
  return null;
}

function success(row: LicenseRow, newlyActivated: boolean): ProtocolResult {
  const remainingSeconds = Math.max(
    0,
    Math.floor((Date.parse(row.expires_at) - Date.now()) / 1000),
  );
  return {
    status: 200,
    body: {
      valid: true,
      code: "OK",
      expiresAt: row.expires_at,
      remainingSeconds,
      newlyActivated,
      modules: parseModules(row.modules_json),
    },
  };
}

async function loadLicense(env: Env, key: string): Promise<LicenseRow | null> {
  const digest = await licenseDigest(key, env.ALBIONMKT_KEY_PEPPER);
  return env.DB.prepare("SELECT * FROM licenses WHERE key_digest = ?1")
    .bind(digest)
    .first<LicenseRow>();
}

export function parseLicenseRequest(payload: unknown): LicenseRequest | null {
  if (!payload || typeof payload !== "object") return null;
  const candidate = payload as Record<string, unknown>;
  if (
    !validateKey(candidate.key) ||
    !validateHwid(candidate.hwid) ||
    !validateVersion(candidate.appVersion)
  ) {
    return null;
  }
  return {
    key: normalizeKey(candidate.key),
    hwid: candidate.hwid.toLowerCase(),
    appVersion: candidate.appVersion,
  };
}

export async function activateLicense(env: Env, request: LicenseRequest): Promise<ProtocolResult> {
  const now = utcNow();
  let row = await loadLicense(env, request.key);
  const licenseError = checkLicense(row, now);
  if (licenseError) return licenseError;
  if (!row) return error("INVALID_KEY", "Key invalida.", 404);

  const deviceDigest = await hwidDigest(request.hwid, env.ALBIONMKT_KEY_PEPPER);
  const existing = await env.DB.prepare(
    "SELECT 1 AS present FROM license_devices WHERE license_id = ?1 AND hwid_digest = ?2",
  )
    .bind(row.id, deviceDigest)
    .first<{ present: number }>();

  const write = await env.DB.prepare(
    `INSERT INTO license_devices
       (license_id, hwid_digest, first_seen_at, last_seen_at, app_version)
     SELECT ?1, ?2, ?3, ?3, ?4
     WHERE EXISTS (
       SELECT 1 FROM licenses
       WHERE id = ?1 AND revoked_at IS NULL AND expires_at > ?3
     )
     AND (
       EXISTS (
         SELECT 1 FROM license_devices
         WHERE license_id = ?1 AND hwid_digest = ?2
       )
       OR (
         SELECT COUNT(*) FROM license_devices WHERE license_id = ?1
       ) < (
         SELECT device_limit FROM licenses WHERE id = ?1
       )
     )
     ON CONFLICT(license_id, hwid_digest) DO UPDATE SET
       last_seen_at = excluded.last_seen_at,
       app_version = excluded.app_version`,
  )
    .bind(row.id, deviceDigest, now, request.appVersion)
    .run();

  if ((write.meta.changes ?? 0) !== 1) {
    row = await loadLicense(env, request.key);
    const changedState = checkLicense(row, utcNow());
    if (changedState) return changedState;
    return error("DEVICE_LIMIT", "O limite de computadores desta key foi atingido.");
  }
  return success(row, existing === null);
}

export async function validateLicense(env: Env, request: LicenseRequest): Promise<ProtocolResult> {
  const now = utcNow();
  const row = await loadLicense(env, request.key);
  const licenseError = checkLicense(row, now);
  if (licenseError) return licenseError;
  if (!row) return error("INVALID_KEY", "Key invalida.", 404);

  const deviceDigest = await hwidDigest(request.hwid, env.ALBIONMKT_KEY_PEPPER);
  const updated = await env.DB.prepare(
    `UPDATE license_devices
     SET last_seen_at = ?1, app_version = ?2
     WHERE license_id = ?3 AND hwid_digest = ?4`,
  )
    .bind(now, request.appVersion, row.id, deviceDigest)
    .run();
  if ((updated.meta.changes ?? 0) !== 1) {
    return error("NOT_ACTIVATED", "Este computador ainda nao foi ativado.");
  }
  return success(row, false);
}

function integer(value: unknown, fallback: number, minimum: number, maximum: number): number | null {
  const resolved = value === undefined || value === null ? fallback : value;
  if (!Number.isInteger(resolved) || Number(resolved) < minimum || Number(resolved) > maximum) {
    return null;
  }
  return Number(resolved);
}

export function parseCreateInput(payload: unknown): CreateLicenseInput | null {
  if (!payload || typeof payload !== "object") return null;
  const candidate = payload as Record<string, unknown>;
  const durationDays = candidate.duration_days === null
    ? null
    : integer(candidate.duration_days, 30, 1, 3650);
  const durationHours = candidate.duration_hours === null || candidate.duration_hours === undefined
    ? null
    : integer(candidate.duration_hours, 0, 1, 87_600);
  const deviceLimit = integer(candidate.device_limit, 1, 1, 25);
  if (deviceLimit === null || (durationDays === null && durationHours === null)) return null;
  if (durationDays !== null && durationHours !== null && candidate.duration_days !== undefined) {
    return null;
  }

  const sourceModules = candidate.modules ?? ["purchase_orders", "sales_orders"];
  if (!Array.isArray(sourceModules) || sourceModules.length === 0) return null;
  const modules = [...new Set(sourceModules)];
  if (
    modules.some(
      (module) => module !== "purchase_orders" && module !== "sales_orders",
    )
  ) {
    return null;
  }
  const discordUserId = candidate.discord_user_id;
  if (
    discordUserId !== undefined &&
    discordUserId !== null &&
    (typeof discordUserId !== "string" || !/^\d{1,32}$/.test(discordUserId))
  ) {
    return null;
  }
  const notes = candidate.notes ?? "";
  if (typeof notes !== "string" || notes.length > 500) return null;
  return {
    discord_user_id: (discordUserId as string | null | undefined) ?? null,
    duration_days: durationDays,
    duration_hours: durationHours,
    device_limit: deviceLimit,
    modules: modules as ModuleId[],
    notes,
  };
}

export async function createLicense(env: Env, input: CreateLicenseInput): Promise<Record<string, unknown>> {
  const createdAt = new Date();
  const durationMs = input.duration_hours !== null
    ? input.duration_hours * 60 * 60 * 1000
    : (input.duration_days ?? 30) * 24 * 60 * 60 * 1000;
  const expiresAt = new Date(createdAt.getTime() + durationMs);

  for (let attempt = 0; attempt < 10; attempt += 1) {
    const key = generateLicenseKey();
    const id = crypto.randomUUID();
    const digest = await licenseDigest(key, env.ALBIONMKT_KEY_PEPPER);
    try {
      await env.DB.prepare(
        `INSERT INTO licenses
          (id, key_digest, key_preview, discord_user_id, created_at, expires_at,
           device_limit, modules_json, notes)
         VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)`,
      )
        .bind(
          id,
          digest,
          maskedKey(key),
          input.discord_user_id,
          createdAt.toISOString(),
          expiresAt.toISOString(),
          input.device_limit,
          JSON.stringify(input.modules),
          input.notes,
        )
        .run();
      return {
        id,
        key,
        key_preview: maskedKey(key),
        expires_at: expiresAt.toISOString(),
        device_limit: input.device_limit,
        modules: input.modules,
      };
    } catch (caught) {
      if (attempt === 9) throw caught;
    }
  }
  throw new Error("nao foi possivel gerar uma key unica");
}

interface SummaryRow extends LicenseRow {
  device_count: number;
  last_activity: string | null;
}

export async function listLicenses(
  env: Env,
  limit: number,
  discordUserId?: string,
): Promise<Record<string, unknown>[]> {
  const constrained = Math.max(1, Math.min(200, Math.trunc(limit)));
  const where = discordUserId ? "WHERE l.discord_user_id = ?1" : "";
  const limitPosition = discordUserId ? "?2" : "?1";
  const statement = env.DB.prepare(
    `SELECT l.*, COUNT(d.hwid_digest) AS device_count,
            MAX(d.last_seen_at) AS last_activity
     FROM licenses l
     LEFT JOIN license_devices d ON d.license_id = l.id
     ${where}
     GROUP BY l.id
     ORDER BY l.created_at DESC
     LIMIT ${limitPosition}`,
  );
  const result = discordUserId
    ? await statement.bind(discordUserId, constrained).all<SummaryRow>()
    : await statement.bind(constrained).all<SummaryRow>();
  return result.results.map((row) => ({
    id: row.id,
    key_preview: row.key_preview,
    discord_user_id: row.discord_user_id,
    created_at: row.created_at,
    expires_at: row.expires_at,
    revoked_at: row.revoked_at,
    device_limit: row.device_limit,
    device_count: row.device_count,
    modules: parseModules(row.modules_json),
    notes: row.notes,
    last_activity: row.last_activity,
  }));
}

export async function revokeLicense(env: Env, id: string): Promise<boolean> {
  const result = await env.DB.prepare(
    "UPDATE licenses SET revoked_at = ?1 WHERE id = ?2 AND revoked_at IS NULL",
  )
    .bind(utcNow(), id)
    .run();
  return (result.meta.changes ?? 0) === 1;
}

export async function resetLicenseDevices(env: Env, id: string): Promise<boolean> {
  const existing = await env.DB.prepare("SELECT 1 AS present FROM licenses WHERE id = ?1")
    .bind(id)
    .first<{ present: number }>();
  if (!existing) return false;
  await env.DB.prepare("DELETE FROM license_devices WHERE license_id = ?1").bind(id).run();
  return true;
}

export async function extendLicense(env: Env, id: string, days: number): Promise<string | null> {
  if (!Number.isInteger(days) || days < 1 || days > 3650) return null;
  const row = await env.DB.prepare("SELECT expires_at FROM licenses WHERE id = ?1")
    .bind(id)
    .first<{ expires_at: string }>();
  if (!row) return null;
  const base = Math.max(Date.now(), Date.parse(row.expires_at));
  const expiration = new Date(base + days * 24 * 60 * 60 * 1000).toISOString();
  await env.DB.prepare("UPDATE licenses SET expires_at = ?1 WHERE id = ?2")
    .bind(expiration, id)
    .run();
  return expiration;
}

export async function licenseStats(env: Env): Promise<Record<string, number>> {
  const now = utcNow();
  const soon = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString();
  const row = await env.DB.prepare(
    `SELECT
       SUM(CASE WHEN revoked_at IS NULL AND expires_at > ?1 THEN 1 ELSE 0 END) AS active,
       SUM(CASE WHEN revoked_at IS NULL AND expires_at > ?1 AND expires_at <= ?2 THEN 1 ELSE 0 END) AS soon,
       SUM(CASE WHEN revoked_at IS NULL AND expires_at <= ?1 THEN 1 ELSE 0 END) AS expired,
       SUM(CASE WHEN revoked_at IS NOT NULL THEN 1 ELSE 0 END) AS revoked,
       COUNT(*) AS total
     FROM licenses`,
  )
    .bind(now, soon)
    .first<{ active: number | null; soon: number | null; expired: number | null; revoked: number | null; total: number }>();
  const devices = await env.DB.prepare("SELECT COUNT(*) AS total FROM license_devices")
    .first<{ total: number }>();
  return {
    active: row?.active ?? 0,
    expires_within_7_days: row?.soon ?? 0,
    expired: row?.expired ?? 0,
    revoked: row?.revoked ?? 0,
    devices: devices?.total ?? 0,
    total: row?.total ?? 0,
  };
}
