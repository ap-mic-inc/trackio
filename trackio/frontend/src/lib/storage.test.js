import { describe, expect, it } from "vitest";
import { diskStatus, formatBytes, storageRows } from "./storage.js";

describe("formatBytes", () => {
  it("picks a readable unit", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(999)).toBe("999 B");
    expect(formatBytes(1536)).toBe("1.5 KB");
    expect(formatBytes(5.2 * 1024 * 1024)).toBe("5.2 MB");
    expect(formatBytes(250 * 1024 ** 3)).toBe("250 GB");
    expect(formatBytes(undefined)).toBe("—");
  });
});

describe("storageRows", () => {
  it("builds per-category cells and totals and marks the selected project", () => {
    const usage = {
      projects: [
        { project: "big", total: 30, database: { bytes: 10 }, artifacts: { bytes: 20 } },
        { project: "small", total: 5, files: { bytes: 5 } },
      ],
    };
    const { rows, totals, total } = storageRows(usage, "small");
    expect(rows.map((r) => [r.project, r.selected])).toEqual([
      ["big", false],
      ["small", true],
    ]);
    expect(rows[0].cells).toEqual([10, 0, 0, 20, 0]);
    expect(totals).toEqual([10, 0, 5, 20, 0]);
    expect(total).toBe(35);
  });

  it("handles missing usage", () => {
    expect(storageRows(null)).toEqual({ rows: [], totals: [0, 0, 0, 0, 0], total: 0 });
  });
});

describe("diskStatus", () => {
  it("flags low free space", () => {
    expect(diskStatus({ total: 100, free: 5 })).toEqual({
      free: 5,
      total: 100,
      usedPercent: 95,
      low: true,
    });
    expect(diskStatus({ total: 100, free: 50 }).low).toBe(false);
    expect(diskStatus(null)).toBeNull();
  });
});
