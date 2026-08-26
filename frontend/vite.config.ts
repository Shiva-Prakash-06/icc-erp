import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";

export default defineConfig({
  root: resolve(__dirname, ".."),
  base: "/static/ui/",
  plugins: [react()],
  build: {
    assetsInlineLimit: 0,
    outDir: resolve(__dirname, "../app/static/ui"),
    emptyOutDir: true,
    manifest: "manifest.json",
    target: "es2022",
    cssCodeSplit: true,
    rollupOptions: {
      input: {
        aurora: resolve(__dirname, "src/entries/aurora.tsx"),
        public: resolve(__dirname, "src/entries/public.ts"),
      },
      output: {
        entryFileNames: "assets/[name]-[hash].js",
        chunkFileNames: "assets/[name]-[hash].js",
        assetFileNames: "assets/[name]-[hash][extname]",
      },
    },
  },
});
