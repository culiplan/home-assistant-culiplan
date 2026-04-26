#!/usr/bin/env node
/**
 * Build Culiplan Lovelace card bundles.
 *
 * Bundles each card .ts source into a self-contained .js file under
 * lovelace/cards/dist/. The bundle inlines lit so HA loads zero external
 * dependencies at runtime (privacy + reliability + supply-chain safety).
 *
 * Usage:
 *   pnpm install
 *   pnpm build:cards
 *
 * Verifies that no http(s):// imports remain in the output (task-1415).
 */
import * as esbuild from "esbuild";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const cardsDir = resolve(__dirname, "cards");
const distDir = resolve(cardsDir, "dist");

const CARDS = [
  { src: "kitchen-dashboard.ts",    out: "kitchen-dashboard.js"    },
  { src: "pantry-tracker.ts",       out: "pantry-tracker.js"       },
  { src: "cooking-mode.ts",         out: "cooking-mode.js"         }, // Phase 3, task-1383
  { src: "blueprint-generator.ts",  out: "blueprint-generator.js"  }, // Phase 3, task-1400
];

const BANNER = `/**
 * Culiplan Lovelace Card — pre-built distribution bundle.
 * Built from lovelace/cards/<source>.ts via esbuild.
 * lit is INLINED — this file has zero runtime external imports.
 *
 * Source-of-truth: see lovelace/cards/<source>.ts in the repo for
 * the un-bundled, type-checked source.
 */
`;

async function build() {
  console.log("Building Culiplan Lovelace cards…");

  for (const { src, out } of CARDS) {
    const entryPoint = resolve(cardsDir, src);
    const outfile    = resolve(distDir,  out);

    await esbuild.build({
      entryPoints: [entryPoint],
      bundle:      true,
      format:      "esm",
      platform:    "browser",
      target:      "es2020",
      outfile,
      banner:      { js: BANNER },
      minify:      false,           // readable for HA reviewers
      treeShaking: true,
      legalComments: "inline",
      logLevel:    "info",
    });

    // Sanity check: no http:// or https:// imports may remain in the bundle
    const bundled = readFileSync(outfile, "utf8");
    const externalImportPattern =
      /from\s+["']https?:\/\/|import\s*\(\s*["']https?:\/\//;
    if (externalImportPattern.test(bundled)) {
      throw new Error(
        `❌ ${out} still contains an external http(s) import. ` +
        `Bundle did not inline a dependency.`,
      );
    }

    const sizeKb = (bundled.length / 1024).toFixed(1);
    console.log(`✓ ${out} — ${sizeKb} KB, no external imports`);
  }

  console.log("All cards bundled successfully.");
}

build().catch((err) => {
  console.error("Build failed:", err);
  process.exit(1);
});
