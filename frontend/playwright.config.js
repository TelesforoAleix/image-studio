import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./checks",
  outputDir: "/tmp/image-studio-browser-results",
  fullyParallel: true,
  use: {
    baseURL: "http://127.0.0.1:5173",
    viewport: { width: 1440, height: 1000 },
  },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1",
    url: "http://127.0.0.1:5173",
    reuseExistingServer: !process.env.CI,
  },
});
