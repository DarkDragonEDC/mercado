declare namespace Cloudflare {
  interface Env {
    DB: D1Database;
    ALBIONMKT_ADMIN_TOKEN: string;
    ALBIONMKT_KEY_PEPPER: string;
    DISCORD_PUBLIC_KEY?: string;
    DISCORD_GUILD_ID?: string;
    DISCORD_ADMIN_USER_IDS?: string;
    TEST_MIGRATIONS: D1Migration[];
  }
}
