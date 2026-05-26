import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      input: {
        demo: "index.html",
        widget: "widget.html",
        loader: "src/loader.ts"
      },
      output: {
        entryFileNames: (chunk) =>
          chunk.name === "loader" ? "widget-loader.js" : "assets/[name]-[hash].js"
      }
    }
  }
});
