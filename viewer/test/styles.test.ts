import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const css = readFileSync(new URL("../src/styles.css", import.meta.url), "utf-8");
const SCALE = { "--fs-display": 20, "--fs-title": 15, "--fs-body": 13, "--fs-label": 11, "--fs-micro": 10 };

describe("type scale", () => {
  it("defines the five sizes, none above 20px", () => {
    for (const [name, px] of Object.entries(SCALE)) expect(css).toContain(`${name}: ${px}px;`);
  });

  it("sets every font size from the scale (no stray sizes anywhere)", () => {
    const sizes = [...css.matchAll(/font-size:\s*([^;]+);/g)].map((m) => m[1].trim());
    expect(sizes.length).toBeGreaterThan(10);
    for (const s of sizes) expect(Object.keys(SCALE).map((k) => `var(${k})`)).toContain(s);
    for (const m of css.matchAll(/\bfont:\s*[^;]*?(\d+)px/g)) expect(Number(m[1])).toBeLessThanOrEqual(20);
  });

  it("uses only the three weights", () => {
    const weights = new Set([...css.matchAll(/font-weight:\s*(\d+)/g)].map((m) => Number(m[1])));
    for (const w of weights) expect([400, 500, 600]).toContain(w);
  });
});
