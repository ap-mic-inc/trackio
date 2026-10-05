import { describe, expect, test } from "vitest";
import {
  dashboardServerUrl,
  maskedToken,
  tokenUsageSnippet,
} from "./apiTokens.js";

describe("maskedToken", () => {
  test("shows the prefix and last characters only", () => {
    expect(maskedToken({ hint: "a1b2" })).toBe("trk_…a1b2");
  });
});

describe("tokenUsageSnippet", () => {
  test("uses the fresh token when available", () => {
    expect(tokenUsageSnippet("https://t.example.com", "trk_abc")).toBe(
      "export TRACKIO_SERVER_URL=https://t.example.com\nexport TRACKIO_WRITE_TOKEN=trk_abc",
    );
  });

  test("falls back to a placeholder", () => {
    expect(tokenUsageSnippet("https://t.example.com", null)).toContain(
      "TRACKIO_WRITE_TOKEN=trk_...",
    );
  });
});

describe("dashboardServerUrl", () => {
  test("joins origin and base path without trailing slash", () => {
    expect(dashboardServerUrl({ origin: "https://t.example.com" }, "/trackio/")).toBe(
      "https://t.example.com/trackio",
    );
    expect(dashboardServerUrl({ origin: "http://localhost:7860" })).toBe(
      "http://localhost:7860",
    );
  });
});
