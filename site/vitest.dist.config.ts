import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["tests/dist/**/*.test.ts"],
    environment: "node",
  },
});
