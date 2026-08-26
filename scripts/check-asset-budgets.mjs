import { readFileSync, readdirSync, statSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const output = resolve(root, "app/static/ui");
const manifest = JSON.parse(readFileSync(resolve(output, "manifest.json"), "utf8"));
const entry = manifest["frontend/src/entries/aurora.tsx"];
const publicEntry = manifest["frontend/src/entries/public.ts"];
if (!entry) throw new Error("Aurora production entry is missing from the Vite manifest.");
if (!publicEntry) throw new Error("Public production entry is missing from the Vite manifest.");

const cssBytes = (entry.css || []).reduce((total, file) => total + statSync(resolve(output, file)).size, 0);
const publicCssBytes = (publicEntry.css || []).reduce((total, file) => total + statSync(resolve(output, file)).size, 0);
const jsFiles = readdirSync(resolve(output, "assets")).filter((file) => file.endsWith(".js"));
const jsSizes = jsFiles.map((file) => [file, statSync(resolve(output, "assets", file)).size]);
const sharedJsBytes = jsSizes.reduce((total, [, size]) => total + size, 0);
const islandFailures = jsSizes.filter(([file, size]) => !file.startsWith("aurora-") && size > 35 * 1024);

const failures = [];
if (cssBytes > 45 * 1024) failures.push(`application CSS ${cssBytes} B exceeds 45 KiB`);
if (publicCssBytes > 20 * 1024) failures.push(`public CSS ${publicCssBytes} B exceeds 20 KiB`);
if (sharedJsBytes > 45 * 1024) failures.push(`shared JavaScript ${sharedJsBytes} B exceeds 45 KiB`);
for (const [file, size] of islandFailures) failures.push(`${file} ${size} B exceeds 35 KiB`);
if (jsFiles.some((file) => file.startsWith("animate-"))) failures.push("obsolete shared animation chunk is present");

if (failures.length) throw new Error(failures.join("; "));
console.log(`asset budgets passed: application CSS=${cssBytes} B, public CSS=${publicCssBytes} B, shared JS=${sharedJsBytes} B`);
