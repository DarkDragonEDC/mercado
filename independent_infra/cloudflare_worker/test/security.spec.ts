import { describe, expect, it } from "vitest";
import {
  generateLicenseKey,
  licenseDigest,
  maskedKey,
  verifyDiscordSignature,
} from "../src/security";

function hex(bytes: ArrayBuffer): string {
  return [...new Uint8Array(bytes)]
    .map((value) => value.toString(16).padStart(2, "0"))
    .join("");
}

describe("segurança das licenças", () => {
  it("gera keys aleatórias no formato comercial e mascara a parte secreta", () => {
    const keys = new Set(Array.from({ length: 100 }, () => generateLicenseKey()));
    expect(keys.size).toBe(100);
    for (const key of keys) {
      expect(key).toMatch(/^ALBIONMKT(?:-[A-Z0-9]{5}){4}$/);
      expect(maskedKey(key)).not.toContain(key);
    }
  });

  it("normaliza maiúsculas antes do HMAC", async () => {
    const pepper = "p".repeat(40);
    await expect(licenseDigest(" albionmkt-AAAAA-BBBBB-CCCCC-DDDDD ", pepper))
      .resolves.toBe(await licenseDigest("ALBIONMKT-AAAAA-BBBBB-CCCCC-DDDDD", pepper));
  });

  it("verifica a assinatura e recusa alteração da interação do Discord", async () => {
    const pair = await crypto.subtle.generateKey("Ed25519", true, ["sign", "verify"]);
    const publicKey = hex(await crypto.subtle.exportKey("raw", pair.publicKey));
    const timestamp = String(Math.floor(Date.now() / 1000));
    const body = JSON.stringify({ type: 1 });
    const signature = hex(
      await crypto.subtle.sign(
        "Ed25519",
        pair.privateKey,
        new TextEncoder().encode(timestamp + body),
      ),
    );
    await expect(verifyDiscordSignature(publicKey, signature, timestamp, body)).resolves.toBe(true);
    await expect(verifyDiscordSignature(publicKey, signature, timestamp, body + "x")).resolves.toBe(false);
  });
});
