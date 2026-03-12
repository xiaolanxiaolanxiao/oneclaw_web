import { defineConfig } from "vite";
import { resolve } from "path";
import { createRequire } from "module";
import { fileURLToPath } from "url";

const __dirname = fileURLToPath(new URL(".", import.meta.url));

// Settings HTTP API middleware for web mode
const require = createRequire(import.meta.url);
const { settingsApiMiddleware } = require("./server-api.cjs");

function settingsApiPlugin() {
  return {
    name: "settings-api",
    configureServer(server: any) {
      server.middlewares.use(settingsApiMiddleware);
    },
  };
}

export default defineConfig({
  root: ".",
  base: "/",
  plugins: [settingsApiPlugin()],
  resolve: {
    alias: {
      // The UI source references files outside ui/ via ../../../src/
      // We map these to our local copies at chat-ui/src/
    },
  },
  esbuild: {
    // Lit uses @customElement decorator – esbuild must transform it
    tsconfigRaw: {
      compilerOptions: {
        experimentalDecorators: true,
        useDefineForClassFields: false,
      },
    },
  },
  build: {
    outDir: resolve(__dirname, "dist"),
    emptyOutDir: true,
    sourcemap: true,
    rollupOptions: {
      input: resolve(__dirname, "index.html"),
    },
  },
  server: {
    port: 5173,
    open: false,
    host: true,
  },
  envDir: ".",
});
