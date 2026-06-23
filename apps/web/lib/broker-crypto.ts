// AES-256-GCM for brokerage secrets at rest. The user's Alpaca PAPER key +
// secret are encrypted before they ever touch the database and decrypted only
// when an order is placed. Key = BROKER_ENC_KEY (64 hex chars = 32 bytes),
// server-only env on Vercel. Unset → encryption unavailable (routes 503), so
// a missing key fails closed rather than storing plaintext.

function keyBytes(): Uint8Array<ArrayBuffer> | null {
  const hex = process.env.BROKER_ENC_KEY ?? "";
  if (!/^[0-9a-fA-F]{64}$/.test(hex)) return null;
  const out = new Uint8Array(32);
  for (let i = 0; i < 32; i++) out[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  return out;
}

async function aesKey(usage: KeyUsage[]): Promise<CryptoKey | null> {
  const kb = keyBytes();
  if (!kb) return null;
  return crypto.subtle.importKey("raw", kb, { name: "AES-GCM" }, false, usage);
}

export function encryptionReady(): boolean {
  return keyBytes() !== null;
}

/** Encrypt → base64(iv ‖ ciphertext+tag). Returns null if no key configured. */
export async function encryptSecret(plain: string): Promise<string | null> {
  const key = await aesKey(["encrypt"]);
  if (!key) return null;
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = new Uint8Array(
    await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, new TextEncoder().encode(plain)),
  );
  const buf = new Uint8Array(iv.length + ct.length);
  buf.set(iv);
  buf.set(ct, iv.length);
  let bin = "";
  for (const b of buf) bin += String.fromCharCode(b);
  return btoa(bin);
}

/** Decrypt a base64(iv ‖ ciphertext) blob. Returns null if no key / bad blob. */
export async function decryptSecret(blob: string): Promise<string | null> {
  const key = await aesKey(["decrypt"]);
  if (!key) return null;
  try {
    const raw = Uint8Array.from(atob(blob), (c) => c.charCodeAt(0));
    // new Uint8Array(view) copies into a fresh ArrayBuffer so the type is
    // Uint8Array<ArrayBuffer> (what Web Crypto's BufferSource wants); .slice()
    // would widen to ArrayBufferLike and fail typecheck.
    const iv = new Uint8Array(raw.subarray(0, 12));
    const ct = new Uint8Array(raw.subarray(12));
    const pt = await crypto.subtle.decrypt({ name: "AES-GCM", iv }, key, ct);
    return new TextDecoder().decode(pt);
  } catch {
    return null;
  }
}
