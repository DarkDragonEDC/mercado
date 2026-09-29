export interface Env {
  DB: D1Database;
  ALBIONMKT_ADMIN_TOKEN: string;
  ALBIONMKT_KEY_PEPPER: string;
  DISCORD_PUBLIC_KEY?: string;
  DISCORD_GUILD_ID?: string;
  DISCORD_ADMIN_USER_IDS?: string;
  DISCORD_BOT_TOKEN?: string;
  DISCORD_ROLE_COMPRA_ID?: string;
  DISCORD_ROLE_VENDA_ID?: string;
  DISCORD_ROLE_COMPLETO_ID?: string;
  MERCADOPAGO_ACCESS_TOKEN?: string;
  MERCADOPAGO_WEBHOOK_SECRET?: string;
  PUBLIC_BASE_URL?: string;
  ALBIONMKT_DOWNLOAD_URL?: string;
}

export type ModuleId = "purchase_orders" | "sales_orders";

export interface LicenseRow {
  id: string;
  key_digest: string;
  key_preview: string;
  discord_user_id: string | null;
  created_at: string;
  expires_at: string;
  revoked_at: string | null;
  device_limit: number;
  modules_json: string;
  notes: string;
}

export interface LicenseRequest {
  key: string;
  hwid: string;
  appVersion: string;
}

export interface CreateLicenseInput {
  discord_user_id: string | null;
  duration_days: number | null;
  duration_hours: number | null;
  device_limit: number;
  modules: ModuleId[];
  notes: string;
}

export type CommercialPlanId = "compra" | "venda" | "completo";

export interface CommercialOrderRow {
  id: string;
  discord_user_id: string;
  guild_id: string;
  plan_id: CommercialPlanId;
  amount_cents: number;
  status: "creating" | "pending" | "processing" | "approved" | "rejected" | "cancelled";
  created_at: string;
  updated_at: string;
  preference_id: string | null;
  payment_id: string | null;
  license_id: string | null;
  license_secret: string | null;
  access_expires_at: string | null;
  delivered_at: string | null;
  delivery_error: string;
}
