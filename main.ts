/**
 * main.ts — entry program for make.fun competition "news-image-20261119"
 * ("Sum up 19 November's world news in one image").
 *
 * The entry image (entry.png, drawn by generate.py) sits beside this file.
 * This program validates it and copies its bytes, unchanged, to
 *   <OUTPUT_DIR>/entry.png        (OUTPUT_DIR defaults to "/output")
 *
 * It uses only the Node.js standard library and touches no network.
 * Running it any number of times produces byte-identical output, because
 * the output is a verbatim copy of the checked-in entry.png.
 */

import { createHash } from "node:crypto";
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  statSync,
} from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const MAX_BYTES = 1_048_576; // the competition's 1 MiB cap for the image

function fail(message: string): never {
  console.error(`error: ${message}`);
  process.exit(1);
}

function main(): void {
  const here = dirname(fileURLToPath(import.meta.url));
  const source = join(here, "entry.png");

  if (!existsSync(source)) {
    fail(`entry.png not found beside main.ts (looked in ${here})`);
  }

  const { size } = statSync(source);
  if (size === 0) {
    fail("entry.png is empty");
  }
  if (size > MAX_BYTES) {
    fail(`entry.png is ${size} bytes, over the ${MAX_BYTES}-byte limit`);
  }

  const bytes = readFileSync(source);
  const sha256 = createHash("sha256").update(bytes).digest("hex");

  const outDir = process.env.OUTPUT_DIR ?? "/output";
  mkdirSync(outDir, { recursive: true });
  const target = join(outDir, "entry.png");
  copyFileSync(source, target);

  const written = statSync(target).size;
  if (written !== size) {
    fail(`copy mismatch: wrote ${written} of ${size} bytes to ${target}`);
  }

  console.log(`entry.png: ${size} bytes`);
  console.log(`sha256: ${sha256}`);
  console.log(`written to ${target}`);
}

main();
