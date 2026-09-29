export function systemInfo(config) {
  const info = config?._System;
  return info && typeof info === "object" ? info : null;
}

export function shortGpuName(name) {
  return String(name || "").replace(/^NVIDIA\s+/i, "").trim();
}

export function gpuSummary(info) {
  const gpus = info?.gpu?.gpus || [];
  if (!gpus.length) return null;
  const counts = new Map();
  for (const gpu of gpus) {
    const name = shortGpuName(gpu.name) || "GPU";
    counts.set(name, (counts.get(name) || 0) + 1);
  }
  return [...counts.entries()].map(([name, n]) => `${n} × ${name}`).join(", ");
}

export function placementLabel(info) {
  const d = info?.distributed;
  if (!d) return null;
  const parts = [];
  if (d.node_rank != null) {
    parts.push(d.num_nodes != null ? `node ${d.node_rank} of ${d.num_nodes}` : `node ${d.node_rank}`);
  }
  if (d.rank != null) {
    parts.push(d.world_size != null ? `rank ${d.rank} of ${d.world_size}` : `rank ${d.rank}`);
  }
  if (d.local_rank != null) parts.push(`local rank ${d.local_rank}`);
  return parts.length ? parts.join(" · ") : null;
}

export function nodeRows(runs, runConfigs) {
  const rows = [];
  for (const run of runs || []) {
    const info = systemInfo(runConfigs?.[run.id]);
    if (!info) continue;
    rows.push({
      run: run.name,
      runId: run.id,
      host: info.hostname || "—",
      nodeRank: info.distributed?.node_rank ?? null,
      placement: placementLabel(info),
      gpus: gpuSummary(info),
      cpu: info.cpu?.model || null,
      memoryGb: info.cpu?.memory_gb ?? null,
      driver: info.gpu?.driver_version || null,
      cuda: info.gpu?.cuda_driver_version || null,
    });
  }
  return rows.sort(
    (a, b) =>
      (a.nodeRank ?? Infinity) - (b.nodeRank ?? Infinity) || a.run.localeCompare(b.run),
  );
}

export const DEVICE_SCOPE_SEPARATOR = " · ";

function runKey(run) {
  return run?.id ?? run?.name;
}

export function hostLabel(info) {
  if (!info) return null;
  if (info.hostname) return String(info.hostname);
  const rank = info.distributed?.node_rank;
  return rank != null ? `node ${rank}` : null;
}

export function deviceScopes(runs, runConfigs) {
  const hosts = new Map();
  for (const run of runs || []) {
    hosts.set(runKey(run), {
      host: hostLabel(systemInfo(runConfigs?.[run.id])),
      name: run.name,
    });
  }
  const distinct = new Set([...hosts.values()].map((h) => h.host).filter(Boolean));
  const scopes = new Map();
  for (const [key, { host, name }] of hosts) {
    scopes.set(key, distinct.size > 1 ? host || name || "" : "");
  }
  return scopes;
}

export function deviceKey(scope, label) {
  return scope ? `${scope}${DEVICE_SCOPE_SEPARATOR}${label}` : label;
}

export function splitDeviceKey(key) {
  const at = String(key).lastIndexOf(DEVICE_SCOPE_SEPARATOR);
  if (at < 0) return { scope: "", label: String(key) };
  return {
    scope: key.slice(0, at),
    label: key.slice(at + DEVICE_SCOPE_SEPARATOR.length),
  };
}

const naturalCompare = (a, b) => a.localeCompare(b, undefined, { numeric: true });

export function sortDeviceKeys(keys) {
  return [...new Set(keys)].sort((a, b) => {
    const x = splitDeviceKey(a);
    const y = splitDeviceKey(b);
    return naturalCompare(x.scope, y.scope) || naturalCompare(x.label, y.label);
  });
}

export function groupDeviceKeys(keys) {
  const groups = [];
  const byScope = new Map();
  for (const key of keys || []) {
    const { scope, label } = splitDeviceKey(key);
    if (!byScope.has(scope)) {
      const group = { scope, devices: [] };
      byScope.set(scope, group);
      groups.push(group);
    }
    byScope.get(scope).devices.push({ key, label });
  }
  return groups;
}

export function gpuModelsByDevice(runs, runConfigs, scopes = deviceScopes(runs, runConfigs)) {
  const names = new Map();
  for (const run of runs || []) {
    const scope = scopes.get(runKey(run)) ?? "";
    for (const gpu of systemInfo(runConfigs?.[run.id])?.gpu?.gpus || []) {
      const key = deviceKey(scope, `GPU ${gpu.index}`);
      if (!names.has(key)) names.set(key, new Set());
      if (gpu.name) names.get(key).add(shortGpuName(gpu.name));
    }
  }
  const models = {};
  for (const [key, set] of names) {
    if (set.size === 1) models[key] = [...set][0];
    else if (set.size > 1) models[key] = `${set.size} models`;
  }
  return models;
}
