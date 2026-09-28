export const STORAGE_CATEGORIES = [
  { key: "database", label: "Database" },
  { key: "media", label: "Media" },
  { key: "files", label: "Files" },
  { key: "artifacts", label: "Artifacts" },
  { key: "traces", label: "Traces" },
];

const UNITS = ["B", "KB", "MB", "GB", "TB", "PB"];

export function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes < 0) return "—";
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const digits = unit === 0 || value >= 100 ? 0 : 1;
  return `${value.toFixed(digits)} ${UNITS[unit]}`;
}

export function storageRows(usage, selectedProject = null) {
  const projects = usage?.projects || [];
  const rows = projects.map((project) => ({
    project: project.project,
    selected: project.project === selectedProject,
    total: project.total || 0,
    cells: STORAGE_CATEGORIES.map(({ key }) => project[key]?.bytes || 0),
  }));
  const totals = STORAGE_CATEGORIES.map((_, i) =>
    rows.reduce((sum, row) => sum + row.cells[i], 0),
  );
  return { rows, totals, total: rows.reduce((sum, row) => sum + row.total, 0) };
}

export function diskStatus(disk, lowFraction = 0.1) {
  if (!disk || !disk.total) return null;
  const freeFraction = disk.free / disk.total;
  return {
    free: disk.free,
    total: disk.total,
    usedPercent: Math.round((1 - freeFraction) * 100),
    low: freeFraction < lowFraction,
  };
}
