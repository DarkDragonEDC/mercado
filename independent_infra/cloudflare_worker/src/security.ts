const KEY_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
const KEY_PATTERN = /^ALBIONMKT(?:-[A-Z0-9]{5}){4}$/;
const HWID_PATTERN = /^[a-fA-F0-9]{64}$/;
const VERSION_PATTERN = /^\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?$/;

function toHex(bytes: ArrayBuffer): string {
  return [...new Uint8Array(bytes)]
    .map((value) => value.toString(16).padStart(2, "0"))
    .join("");
}

function fromHex(value: string): Uint8Array<ArrayBuffer> {
  if (!/^[a-fA-F0-9]*$/.test(value) || value.length % 2 !== 0) {
    throw new Error("hexadecimal invalido");
  }
  const result = new Uint8Array(value.length / 2);
  for (let index = 0; index < value.length; index += 2) {
    result[index / 2] = Number.parseInt(value.slice(index, index + 2), 16);
  }
  return result;
}

export function normalizeKey(value: string): string {
  return value.trim().toUpperCase();
}

export function validateKey(value: unknown): value is string {
  return typeof value === "string" && KEY_PATTERN.test(normalizeKey(value));
}

export function validateHwid(value: unknown): value is string {
  return typeof value === "string" && HWID_PATTERN.test(value);
}

export function validateVersion(value: unknown): value is string {
  return typeof value === "string" && value.length <= 32 && VERSION_PATTERN.test(value);
}

export async function keyedDigest(value: string, pepper: string): Promise<string> {
  if (pepper.length < 32) {
    throw new Error("ALBIONMKT_KEY_PEPPER deve possuir pelo menos 32 caracteres");
  }
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(pepper),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  return toHex(await crypto.subtle.sign("HMAC", key, encoder.encode(value)));
}

export async function licenseDigest(key: string, pepper: string): Promise<string> {
  return keyedDigest(normalizeKey(key), pepper);
}

export async function hwidDigest(hwid: string, pepper: string): Promise<string> {
  return keyedDigest(hwid.trim().toLowerCase(), pepper);
}

export function generateLicenseKey(): string {
  const characters: string[] = [];
  while (characters.length < 20) {
    const bytes = crypto.getRandomValues(new Uint8Array(32));
    for (const byte of bytes) {
      if (byte >= 252) continue;
      characters.push(KEY_ALPHABET[byte % KEY_ALPHABET.length] ?? "A");
      if (characters.length === 20) break;
    }
  }
  const groups = [0, 5, 10, 15].map((start) => characters.slice(start, start + 5).join(""));
  return `ALBIONMKT-${groups.join("-")}`;
}

export function maskedKey(key: string): string {
  const normalized = normalizeKey(key);
  return `${normalized.slice(0, 14)}...${normalized.slice(-5)}`;
}

export async function safeSecretMatches(provided: string, expected: string): Promise<boolean> {
  if (expected.length < 32) return false;
  const [providedDigest, expectedDigest] = await Promise.all([
    keyedDigest(provided, expected),
    keyedDigest(expected, expected),
  ]);
  let difference = providedDigest.length ^ expectedDigest.length;
  const length = Math.max(providedDigest.length, expectedDigest.length);
  for (let index = 0; index < length; index += 1) {
    difference |= (providedDigest.charCodeAt(index) || 0) ^ (expectedDigest.charCodeAt(index) || 0);
  }
  return difference === 0;
}

export async function verifyDiscordSignature(
  publicKeyHex: string,
  signatureHex: string,
  timestamp: string,
  body: string,
): Promise<boolean> {
  try {
    if (publicKeyHex.length !== 64 || signatureHex.length !== 128) return false;
    const timestampMs = Number(timestamp) * 1000;
    if (!Number.isFinite(timestampMs) || Math.abs(Date.now() - timestampMs) > 5 * 60 * 1000) {
      return false;
    }
    const publicKey = await crypto.subtle.importKey(
      "raw",
      fromHex(publicKeyHex),
      { name: "Ed25519" },
      false,
      ["verify"],
    );
    return crypto.subtle.verify(
      "Ed25519",
      publicKey,
      fromHex(signatureHex),
      new TextEncoder().encode(timestamp + body),
    );
  } catch {
    return false;
  }
}
