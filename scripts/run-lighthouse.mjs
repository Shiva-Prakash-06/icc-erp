import fs from "node:fs/promises";
import path from "node:path";
import lighthouse from "lighthouse";
import * as chromeLauncher from "chrome-launcher";
import desktopConfig from "lighthouse/core/config/desktop-config.js";

const outputDirectory = path.resolve("test-results/lighthouse");
await fs.mkdir(outputDirectory, { recursive: true });

const chrome = await chromeLauncher.launch({ chromeFlags: ["--headless=new", "--no-sandbox"] });
const profiles = [
  { name: "desktop", config: desktopConfig, performance: 0.90 },
  { name: "mobile", config: undefined, performance: 0.85 },
];
const failures = [];

try {
  for (const profile of profiles) {
    const result = await lighthouse("http://127.0.0.1:5010/public/", {
      port: chrome.port,
      output: "json",
      logLevel: "error",
      onlyCategories: ["performance", "accessibility", "best-practices"],
    }, profile.config);
    if (!result) throw new Error(`Lighthouse returned no result for ${profile.name}`);
    await fs.writeFile(path.join(outputDirectory, `${profile.name}.json`), result.report);
    const { lhr } = result;
    const measured = {
      accessibility: lhr.categories.accessibility.score,
      bestPractices: lhr.categories["best-practices"].score,
      performance: lhr.categories.performance.score,
      cls: lhr.audits["cumulative-layout-shift"].numericValue,
      lcpMs: lhr.audits["largest-contentful-paint"].numericValue,
      tbtMs: lhr.audits["total-blocking-time"].numericValue,
    };
    const gates = {
      accessibility: measured.accessibility === 1,
      bestPractices: measured.bestPractices >= 0.95,
      performance: measured.performance >= profile.performance,
      cls: measured.cls < 0.1,
      lcp: measured.lcpMs < 2500,
      tbt: measured.tbtMs < 200,
    };
    for (const [gate, passed] of Object.entries(gates)) {
      if (!passed) failures.push(`${profile.name}.${gate}`);
    }
    console.log(`${profile.name}: ${JSON.stringify(measured)}`);
  }
} finally {
  await chrome.kill();
}

if (failures.length) {
  throw new Error(`Lighthouse gates failed: ${failures.join(", ")}`);
}
