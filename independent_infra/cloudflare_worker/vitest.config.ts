import path from "node:path";
import { fileURLToPath } from "node:url";
import { cloudflareTest, readD1Migrations } from "@cloudflare/vitest-plugin";
import { defineConfig } from "vitest/config";

const directory = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [
    cloudflareTest(async () => ({
      main: path.join(directory, "src/index.ts"),
      miniflare: {
        compatibilityDate: "2026-08-26",
        d1Databases: ["DB"],
        bindings: {
          TEST_MIGRATIONS: await readD1Migrations(path.join(directory, "migrations")),
          ALBIONMKT_ADMIN_TOKEN: "test-admin-token-000000000000000000000000",
          ALBIONMKT_KEY_PEPPER: "test-key-pepper-0000000000000000000000000",
          DISCORD_PUBLIC_KEY: "0".repeat(64),
          DISCORD_GUILD_ID: "1541428118533967972",
          DISCORD_ADMIN_USER_IDS: "1366066241667862680",
        },
      },
    })),
  ],
  test: {
    setupFiles: ["./test/apply-migrations.ts"],
  },
});
