import { afterEach, beforeEach, expect, it, vi } from "vitest";

vi.mock("./staticApi.js", () => ({
  initialize: vi.fn(),
  getProjectSummary: vi.fn().mockResolvedValue({ runs: [{ id: "a", name: "same" }, { id: "b", name: "same" }] }),
  getLogs: vi.fn().mockImplementation(async (_project, run) => run.id === "a" ? [{ timestamp: "2026-01-01T00:00:00Z", step: 1, loss: 0.5 }] : []),
}));

beforeEach(() => {
  vi.resetModules();
  vi.stubGlobal("window", { __trackio_base: "/dashboard" });
  vi.stubGlobal("sessionStorage", { getItem: () => null });
});

afterEach(() => vi.unstubAllGlobals());

it("fetches the compact live endpoint with the abort signal", async () => {
  const result = { runs: [], tail_rows: 50, server_time: "2026-01-01T00:00:00Z" };
  const fetch = vi.fn()
    .mockResolvedValueOnce({ ok: false })
    .mockResolvedValueOnce({ ok: true, json: async () => ({ data: result }) });
  vi.stubGlobal("fetch", fetch);
  const { getRunStatus } = await import("./api.js");
  const controller = new AbortController();
  expect(await getRunStatus("project", { signal: controller.signal })).toEqual(result);
  expect(fetch).toHaveBeenLastCalledWith("/dashboard/api/get_run_status", expect.objectContaining({
    method: "POST", body: '{"project":"project"}', signal: controller.signal,
  }));
});

it("summarizes static snapshots without calling the live endpoint", async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ mode: "static" }) });
  vi.stubGlobal("fetch", fetch);
  const { getRunStatus } = await import("./api.js");
  const result = await getRunStatus("project");
  expect(result.snapshot).toBe(true);
  expect(result.runs.map((run) => run.id)).toEqual(["a", "b"]);
  expect(result.runs[0].metrics.loss.last).toBe(0.5);
  expect(result.runs[1].metrics).toEqual({});
  expect(fetch).toHaveBeenCalledTimes(1);
});

it("does not start a live request after cancellation during mode detection", async () => {
  const controller = new AbortController();
  const fetch = vi.fn().mockImplementation(async () => {
    controller.abort();
    return { ok: false };
  });
  vi.stubGlobal("fetch", fetch);
  const { getRunStatus } = await import("./api.js");
  await expect(getRunStatus("project", { signal: controller.signal })).rejects.toThrow();
  expect(fetch).toHaveBeenCalledTimes(1);
});
