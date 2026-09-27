export function summarizeRun(record, logs, tailRows = 50) {
  const ordered = logs.map((row, index) => ({ row, index })).sort(
    (a, b) => new Date(b.row.timestamp) - new Date(a.row.timestamp) || b.index - a.index,
  );
  const tail = ordered.slice(0, tailRows).map(({ row }) => row);
  const metrics = {};
  for (const row of tail) {
    for (const [name, value] of Object.entries(row)) {
      if (name === "timestamp" || name === "step" || typeof value !== "number" || !Number.isFinite(value)) continue;
      if (!Object.hasOwn(metrics, name)) {
        Object.defineProperty(metrics, name, {
          value: { last: value, prev: null, step: row.step, timestamp: row.timestamp },
          enumerable: true,
        });
      } else if (metrics[name].prev == null) {
        metrics[name].prev = value;
      }
    }
  }
  return {
    id: record.id,
    name: record.name,
    first_timestamp: record.created_at ?? ordered.at(-1)?.row.timestamp ?? null,
    last_timestamp: tail[0]?.timestamp ?? null,
    last_step: tail[0]?.step ?? null,
    tail_first_timestamp: tail.at(-1)?.timestamp ?? null,
    tail_first_step: tail.at(-1)?.step ?? null,
    metrics,
  };
}

export function createStatusLoader({ request, onSuccess, onError, onLoading, timeoutMs = 15000 }) {
  let active = null;
  let disposed = false;
  let failures = 0;
  let nextAttempt = 0;

  async function load(force = false) {
    if (disposed || active || (!force && Date.now() < nextAttempt)) return;
    const controller = new AbortController();
    active = controller;
    onLoading(true);
    let timer;
    const cancelled = new Promise((_, reject) => {
      controller.signal.addEventListener("abort", () => reject(controller.signal.reason), { once: true });
      timer = setTimeout(() => controller.abort(new Error("Status request timed out")), timeoutMs);
    });
    try {
      const result = await Promise.race([request(controller.signal), cancelled]);
      if (disposed) return;
      failures = 0;
      nextAttempt = 0;
      onSuccess(result);
    } catch (error) {
      if (disposed) return;
      failures += 1;
      nextAttempt = Date.now() + Math.min(30000, 2000 * 2 ** (failures - 1));
      onError(error);
    } finally {
      clearTimeout(timer);
      active = null;
      if (!disposed) onLoading(false);
    }
  }

  return {
    load,
    dispose() {
      disposed = true;
      active?.abort();
    },
  };
}
