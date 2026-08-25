import { defineConfig } from "vite";
import { resolve } from "node:path";

export default defineConfig({
  build: {
    outDir: ".site-cache/labs",
    emptyOutDir: true,
    sourcemap: false,
    minify: "oxc",
    lib: {
      entry: resolve(import.meta.dirname, "site/labs/src/main.ts"),
      formats: ["es"],
      fileName: () => "cc-agent-lab.js",
    },
    rollupOptions: {
      output: {
        codeSplitting: false,
      },
    },
  },
});
