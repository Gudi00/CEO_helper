import { defineConfig } from "vite";
import { crx } from "@crxjs/vite-plugin";
import { fileURLToPath } from "node:url";
import manifest from "./manifest.json";

export default defineConfig({
  plugins: [crx({ manifest })],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  build: {
    target: "es2022",
    sourcemap: true,
    rollupOptions: {
      input: {
        popup: "src/popup/index.html",
      },
    },
  },
  test: {
    environment: "happy-dom",
    globals: true,
    include: ["tests/**/*.test.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text"],
      include: ["src/**/*.ts"],
      exclude: ["src/**/*.d.ts"],
    },
  },
});
