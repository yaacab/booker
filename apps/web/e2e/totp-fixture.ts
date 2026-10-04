import { createHmac } from "node:crypto";

// Matches the synthetic admin/operator seed only; never use this in application auth.
const DEMO_TOTP_SECRET = "JBSWY3DPEHPK3PXP";

export function demoTotp(): string {
  return fixtureTotp(DEMO_TOTP_SECRET);
}

export function fixtureTotp(secret: string): string {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  const bits = [...secret]
    .map((char) => alphabet.indexOf(char).toString(2).padStart(5, "0"))
    .join("");
  const key = Buffer.from(bits.match(/.{8}/g)!.map((byte) => Number.parseInt(byte, 2)));
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30_000)));
  const digest = createHmac("sha1", key).update(counter).digest();
  return ((digest.readUInt32BE(digest[digest.length - 1] & 15) & 0x7fffffff) % 1_000_000)
    .toString().padStart(6, "0");
}
