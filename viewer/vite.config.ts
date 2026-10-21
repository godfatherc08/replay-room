import { defineConfig } from "vitest/config";

// Bundles are served as static files. By default they come straight from the
// exporter's output (python -m replay_room.render), so the dev harness needs no
// backend; set BUNDLES_DIR to serve another folder. `vite build` copies them
// into dist/ for Azure Static Web Apps.
export default defineConfig({
  base: "./",
  publicDir: process.env.BUNDLES_DIR ?? "../data/accounts",
  assetsInclude: ["**/*.glb"], // the player model is bundled as a static asset
  build: { outDir: "dist", chunkSizeWarningLimit: 1500 },
  test: { environment: "node", include: ["test/**/*.test.ts"] },
});
