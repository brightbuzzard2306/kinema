// Guards a production-only bug we hit: the CSS minifier once dropped the STANDARD `backdrop-filter` from our glass classes,
// leaving only `-webkit-backdrop-filter` (Safari). Chrome/Edge/Firefox then render no frosted glass at all.
// Runs after `next build`. Warns loudly by default (never blocks a deploy over a format change); set CSS_CHECK_STRICT=1 to fail instead.
import { readdirSync, readFileSync, existsSync } from "node:fs";
import { join } from "node:path";

const dir = join(process.cwd(), ".next", "static", "chunks");
if (!existsSync(dir)) {
  console.log("verify-css: no .next/static/chunks (skipped)");
  process.exit(0);
}
const css = readdirSync(dir).filter((f) => f.endsWith(".css")).map((f) => readFileSync(join(dir, f), "utf8")).join("\n");
const missing = [];
for (const cls of [".glass", ".glass-strong", ".glass-pill"]) {
  const start = css.indexOf(`${cls}{`);
  if (start === -1) continue;
  const body = css.slice(start, css.indexOf("}", start));
  const standard = body.replace(/-webkit-backdrop-filter/g, "").includes("backdrop-filter:");
  if (!standard) missing.push(cls);
}
if (missing.length) {
  console.error(`\nverify-css: WARNING - standard backdrop-filter is missing from ${missing.join(", ")}. Glass blur will not show in Chrome/Edge/Firefox.\n`);
  process.exit(process.env.CSS_CHECK_STRICT === "1" ? 1 : 0);
}
console.log("verify-css: glass classes keep the standard backdrop-filter (ok)");
