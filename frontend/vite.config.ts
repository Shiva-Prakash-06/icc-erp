import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";

export default defineConfig({
  root: resolve(__dirname, ".."),
  plugins: [react()],
  build: {
    outDir: resolve(__dirname, "../app/static/ui"),
    emptyOutDir: true,
    manifest: "manifest.json",
    target: "es2022",
    cssCodeSplit: true,
    rollupOptions: {
      input: {
        aurora: resolve(__dirname, "src/entries/aurora.tsx"),
      },
      output: {
        entryFileNames: "assets/[name]-[hash].js",
        chunkFileNames: "assets/[name]-[hash].js",
        assetFileNames: "assets/[name]-[hash][extname]",
      },
    },
  },
});
