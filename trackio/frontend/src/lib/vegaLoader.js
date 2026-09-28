let promise = null;
let loaded = null;

export function loadVega() {
  if (!promise) {
    promise = Promise.all([import("vega-embed"), import("vega")]).then(
      ([embedModule, vegaModule]) => {
        loaded = { embed: embedModule.default, vega: vegaModule };
        return loaded;
      },
    );
  }
  return promise;
}

export function getVega() {
  return loaded;
}
