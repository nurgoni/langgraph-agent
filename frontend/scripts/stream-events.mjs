/**
 * Generate tipe TypeScript event SSE dari `contracts/stream-event.schema.json` (F25) ke
 * `src/api/stream-event.d.ts`. Dengan `--check`, gagal (exit 1) jika file tidak sinkron, seperti
 * `openapi-typescript --check` untuk `schema.d.ts`.
 */
import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

import { compileFromFile } from "json-schema-to-typescript";

const SCHEMA_PATH = fileURLToPath(new URL("../../contracts/stream-event.schema.json", import.meta.url));
const OUTPUT_PATH = fileURLToPath(new URL("../src/api/stream-event.d.ts", import.meta.url));
const BANNER = `/**
 * File ini digenerate dari contracts/stream-event.schema.json. Jangan diedit manual.
 * Generate ulang: corepack pnpm generate:api
 */`;

const generated = await compileFromFile(SCHEMA_PATH, {
  bannerComment: BANNER,
  additionalProperties: false,
  unknownAny: true,
  style: { printWidth: 100 },
});

if (process.argv.includes("--check")) {
  const current = await readFile(OUTPUT_PATH, "utf8").catch(() => "");
  if (current !== generated) {
    console.error(`${OUTPUT_PATH} is out of date. Run: corepack pnpm generate:api`);
    process.exit(1);
  }
} else {
  await writeFile(OUTPUT_PATH, generated, "utf8");
}
