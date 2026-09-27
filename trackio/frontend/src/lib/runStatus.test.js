import { afterEach, describe, expect, it, vi } from "vitest";
import { createStatusLoader, summarizeRun } from "./runStatus.js";

afterEach(() => vi.useRealTimers());

function setup(request, extra = {}) {
  const callbacks = { request, onSuccess: vi.fn(), onError: vi.fn(), onLoading: vi.fn(), ...extra };
  return { ...callbacks, loader: createStatusLoader(callbacks) };
}

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

describe("status refresh", () => {
  it("allows only one request while a slow refresh is pending", async () => {
    const pending = deferred();
    const s = setup(vi.fn(() => pending.promise));
    const first = s.loader.load();
    await s.loader.load(true);
    expect(s.request).toHaveBeenCalledTimes(1);
    pending.resolve({ runs: [] });
    await first;
    expect(s.onSuccess).toHaveBeenCalledOnce();
    expect(s.onLoading.mock.calls).toEqual([[true], [false]]);
  });

  it("backs off failures, retains the last successful result, and permits manual retry", async () => {
    vi.useFakeTimers();
    const request = vi.fn().mockResolvedValueOnce({ runs: ["old"] }).mockRejectedValueOnce(new Error("offline")).mockResolvedValue({ runs: ["new"] });
    const s = setup(request);
    await s.loader.load();
    await s.loader.load();
    await s.loader.load();
    expect(request).toHaveBeenCalledTimes(2);
    expect(s.onSuccess).toHaveBeenLastCalledWith({ runs: ["old"] });
    expect(s.onError).toHaveBeenCalledOnce();
    await s.loader.load(true);
    expect(s.onSuccess).toHaveBeenLastCalledWith({ runs: ["new"] });
  });

  it("aborts a timed out request and ignores its eventual response", async () => {
    vi.useFakeTimers();
    const pending = deferred();
    const s = setup(vi.fn(() => pending.promise), { timeoutMs: 100 });
    const first = s.loader.load();
    const signal = s.request.mock.calls[0][0];
    await vi.advanceTimersByTimeAsync(100);
    await first;
    expect(signal.aborted).toBe(true);
    expect(s.onError).toHaveBeenCalledOnce();
    pending.resolve({ runs: ["late"] });
    await Promise.resolve();
    expect(s.onSuccess).not.toHaveBeenCalled();
    expect(s.onLoading).toHaveBeenLastCalledWith(false);
  });

  it("disposes old project requests without publishing stale data or errors", async () => {
    const pending = deferred();
    const s = setup(vi.fn(() => pending.promise));
    const first = s.loader.load();
    const signal = s.request.mock.calls[0][0];
    s.loader.dispose();
    pending.resolve({ runs: ["wrong-project"] });
    await first;
    await s.loader.load();
    expect(signal.aborted).toBe(true);
    expect(s.onSuccess).not.toHaveBeenCalled();
    expect(s.onError).not.toHaveBeenCalled();
    expect(s.request).toHaveBeenCalledOnce();
  });

  it("automatically retries after the backoff expires", async () => {
    vi.useFakeTimers();
    const s = setup(vi.fn().mockRejectedValueOnce(new Error("offline")).mockResolvedValue({ runs: [] }));
    await s.loader.load();
    await vi.advanceTimersByTimeAsync(2000);
    await s.loader.load();
    expect(s.onSuccess).toHaveBeenCalledOnce();
  });
});

describe("snapshot summary", () => {
  it("uses the latest timestamp and insertion order with a bounded numeric tail", () => {
    const result = summarizeRun({ id: "a", name: "same" }, [
      { timestamp: "2026-01-01T00:01:00Z", step: 8, loss: 4, flag: true },
      { timestamp: "2026-01-01T00:00:00Z", step: 100, loss: 9, old: 1 },
      { timestamp: "2026-01-01T00:01:00Z", step: 3, loss: 2, bad: Infinity },
    ], 2);
    expect(result.last_step).toBe(3);
    expect(result.tail_first_step).toBe(8);
    expect(result.first_timestamp).toBe("2026-01-01T00:00:00Z");
    expect(result.metrics).toEqual({ loss: { last: 2, prev: 4, step: 3, timestamp: "2026-01-01T00:01:00Z" } });
  });

  it("keeps runs without logs and metric names that match object properties", () => {
    expect(summarizeRun({ id: "empty", name: "empty" }, []).last_step).toBeNull();
    const logs = [JSON.parse('{"timestamp":"2026-01-01","step":0,"__proto__":1,"constructor":2}')];
    expect(Object.keys(summarizeRun({ id: "a" }, logs).metrics)).toEqual(["__proto__", "constructor"]);
  });
});
