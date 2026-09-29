import { describe, expect, it } from "vitest";
import {
  deviceKey,
  deviceScopes,
  gpuModelsByDevice,
  gpuSummary,
  groupDeviceKeys,
  nodeRows,
  placementLabel,
  sortDeviceKeys,
  splitDeviceKey,
} from "./devices.js";

const h100 = { name: "NVIDIA H100 80GB HBM3" };
const configs = {
  a: {
    _System: {
      hostname: "gpu-node-0",
      distributed: { node_rank: 0, num_nodes: 2, rank: 0, world_size: 16, local_rank: 0 },
      cpu: { model: "AMD EPYC 9654", memory_gb: 1511.7 },
      gpu: {
        driver_version: "550.54.15",
        cuda_driver_version: "12.4",
        gpus: [{ index: 0, ...h100 }, { index: 1, ...h100 }],
      },
    },
  },
  b: {
    _System: {
      hostname: "gpu-node-1",
      distributed: { node_rank: 1, num_nodes: 2 },
      gpu: { gpus: [{ index: 0, name: "NVIDIA A100-SXM4-80GB" }, { index: 1, ...h100 }] },
    },
  },
  c: { lr: 1 },
};
const runs = [
  { id: "b", name: "exp-node1" },
  { id: "a", name: "exp-node0" },
  { id: "c", name: "no-info" },
];

describe("devices", () => {
  it("summarises GPUs by model", () => {
    expect(gpuSummary(configs.a._System)).toBe("2 × H100 80GB HBM3");
    expect(gpuSummary(configs.b._System)).toBe("1 × A100-SXM4-80GB, 1 × H100 80GB HBM3");
    expect(gpuSummary({})).toBeNull();
  });

  it("describes where a run sits in a distributed job", () => {
    expect(placementLabel(configs.a._System)).toBe(
      "node 0 of 2 · rank 0 of 16 · local rank 0",
    );
    expect(placementLabel({})).toBeNull();
  });

  it("builds node rows ordered by node rank, skipping runs without info", () => {
    const rows = nodeRows(runs, configs);
    expect(rows.map((r) => [r.run, r.host])).toEqual([
      ["exp-node0", "gpu-node-0"],
      ["exp-node1", "gpu-node-1"],
    ]);
    expect(rows[0]).toMatchObject({ gpus: "2 × H100 80GB HBM3", driver: "550.54.15", cuda: "12.4" });
  });

  it("scopes devices by host only when runs come from different hosts", () => {
    const scopes = deviceScopes(runs, configs);
    expect(Object.fromEntries(scopes)).toEqual({
      a: "gpu-node-0",
      b: "gpu-node-1",
      c: "no-info",
    });
    const sameHost = deviceScopes([{ id: "a", name: "x" }, { id: "c", name: "y" }], configs);
    expect(Object.fromEntries(sameHost)).toEqual({ a: "", c: "" });
    const byRank = deviceScopes(
      [{ id: "p" }, { id: "q" }],
      {
        p: { _System: { distributed: { node_rank: 0 } } },
        q: { _System: { distributed: { node_rank: 1 } } },
      },
    );
    expect([...byRank.values()]).toEqual(["node 0", "node 1"]);
  });

  it("round-trips, sorts and groups device keys", () => {
    expect(deviceKey("", "GPU 0")).toBe("GPU 0");
    expect(deviceKey("gpu-node-1", "GPU 0")).toBe("gpu-node-1 · GPU 0");
    expect(splitDeviceKey("gpu-node-1 · GPU 0")).toEqual({ scope: "gpu-node-1", label: "GPU 0" });
    expect(splitDeviceKey("GPU 3")).toEqual({ scope: "", label: "GPU 3" });
    const keys = sortDeviceKeys([
      "node-10 · GPU 0",
      "node-2 · GPU 10",
      "node-2 · GPU 2",
      "node-2 · GPU 2",
    ]);
    expect(keys).toEqual(["node-2 · GPU 2", "node-2 · GPU 10", "node-10 · GPU 0"]);
    expect(groupDeviceKeys(keys).map((g) => [g.scope, g.devices.map((d) => d.label)])).toEqual([
      ["node-2", ["GPU 2", "GPU 10"]],
      ["node-10", ["GPU 0"]],
    ]);
  });

  it("names each GPU per host, flagging mixed models on one host", () => {
    expect(gpuModelsByDevice(runs, configs)).toEqual({
      "gpu-node-0 · GPU 0": "H100 80GB HBM3",
      "gpu-node-0 · GPU 1": "H100 80GB HBM3",
      "gpu-node-1 · GPU 0": "A100-SXM4-80GB",
      "gpu-node-1 · GPU 1": "H100 80GB HBM3",
    });
    expect(gpuModelsByDevice([{ id: "a" }], configs)).toEqual({
      "GPU 0": "H100 80GB HBM3",
      "GPU 1": "H100 80GB HBM3",
    });
    const unscoped = new Map([["a", ""], ["b", ""]]);
    expect(gpuModelsByDevice(runs.slice(0, 2), configs, unscoped)["GPU 0"]).toBe("2 models");
  });
});
