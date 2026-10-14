import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const vendor = JSON.parse(readFileSync(join(root, "src/VENDOR.json"), "utf8"));
const digest = (name) => "sha256:" + createHash("sha256").update(readFileSync(join(root, name))).digest("hex");
if (digest("src/protocol.ts") !== vendor.protocol_sha256) throw new Error("protocol hash mismatch");
for (const [name, expected] of Object.entries(vendor.schema_sha256)) {
  if (digest(`src/schemas/${name}.json`) !== expected) throw new Error(`${name} schema hash mismatch`);
}
console.log("TypeScript contract hashes verified");
