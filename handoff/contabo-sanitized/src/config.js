import "dotenv/config";

const required = [
  "DISCORD_TOKEN",
  "DISCORD_CLIENT_ID",
  "DISCORD_GUILD_ID",
  "MERCADO_PAGO_ACCESS_TOKEN",
  "PUBLIC_BASE_URL",
  "LICENSE_PEPPER",
  "LICENSE_ENCRYPTION_KEY"
];

export function validateConfig() {
  const missing = required.filter((key) => !process.env[key]);
  if (missing.length) {
    throw new Error(`Variaveis ausentes: ${missing.join(", ")}`);
  }
}

export const config = {
  discordToken: process.env.DISCORD_TOKEN,
  clientId: process.env.DISCORD_CLIENT_ID,
  guildId: process.env.DISCORD_GUILD_ID,
  subscriberRoleId: process.env.SUBSCRIBER_ROLE_ID || "",
  subscriberRoleName: process.env.SUBSCRIBER_ROLE_NAME || "Assinante",
  visitorRoleId: process.env.VISITOR_ROLE_ID || "",
  visitorRoleName: process.env.VISITOR_ROLE_NAME || "👤・Visitante",
  entryChannelId: process.env.ENTRY_CHANNEL_ID || "",
  mercadoPagoToken: process.env.MERCADO_PAGO_ACCESS_TOKEN,
  mercadoPagoPlanId: (process.env.MERCADO_PAGO_PLAN_ID || "").trim(),
  webhookSecret: process.env.MERCADO_PAGO_WEBHOOK_SECRET || "",
  publicBaseUrl: (process.env.PUBLIC_BASE_URL || "").replace(/\/$/, ""),
  port: Number(process.env.PORT || 3000),
  planName: process.env.PLAN_NAME || "Plano Mensal",
  planPrice: Number(process.env.PLAN_PRICE || 39.9),
  currency: process.env.PLAN_CURRENCY || "BRL",
  accessDays: Number(process.env.ACCESS_DAYS || 30),
  freeTrialEnabled: /^(true|1|yes)$/i.test(process.env.FREE_TRIAL_ENABLED || "true"),
  freeTrialDays: Math.max(1, Number(process.env.FREE_TRIAL_DAYS || 1)),
  freeTrialName: (process.env.FREE_TRIAL_NAME || "Teste gratis").trim(),
  salesEnabled: /^(true|1|yes)$/i.test(process.env.SALES_ENABLED || "false"),
  paymentLink: (process.env.PAYMENT_LINK || "").trim(),
  paymentTestMode: /^(true|1|yes)$/i.test(process.env.PAYMENT_TEST_MODE || "false"),
  testPaymentAmount: Number(process.env.TEST_PAYMENT_AMOUNT || 0.5),
  testPaymentReference: (process.env.TEST_PAYMENT_REFERENCE || "teste").trim(),
  testPaymentDescription: (process.env.TEST_PAYMENT_DESCRIPTION || "Teste").trim(),
  downloadFilePath: (process.env.DOWNLOAD_FILE_PATH || "").trim(),
  downloadSecret: process.env.DOWNLOAD_SECRET || "",
  downloadLinkDays: Number(process.env.DOWNLOAD_LINK_DAYS || 7),
  logChannelId: (process.env.LOG_CHANNEL_ID || "").trim(),
  supportChannelId: (process.env.SUPPORT_CHANNEL_ID || "").trim(),
  salesChannelId: (process.env.SALES_CHANNEL_ID || "").trim(),
  salesControlChannelId: (process.env.SALES_CONTROL_CHANNEL_ID || "").trim(),
  licenseMonitorChannelId: (process.env.LICENSE_MONITOR_CHANNEL_ID || "").trim(),
  genericLicenseKey: (process.env.GENERIC_LICENSE_KEY || "ALBIONMKT-EXEMPLO-0001").trim(),
  licenseGistRawUrl: (process.env.LICENSE_GIST_RAW_URL || "").trim(),
  licensePepper: (process.env.LICENSE_PEPPER || "").trim(),
  licenseEncryptionKey: (process.env.LICENSE_ENCRYPTION_KEY || "").trim()
};
