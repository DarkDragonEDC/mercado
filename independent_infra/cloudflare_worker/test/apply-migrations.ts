import { env } from "cloudflare:workers";
import { applyD1Migrations } from "cloudflare:test";

await applyD1Migrations(
  (env as Cloudflare.Env).DB,
  (env as Cloudflare.Env).TEST_MIGRATIONS,
);
