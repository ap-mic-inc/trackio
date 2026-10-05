export const API_TOKEN_PREFIX = "trk_";

/**
 * Masked display form of a stored token, e.g. `trk_…a1b2`.
 * @param {{hint?: string}} token
 * @returns {string}
 */
export function maskedToken(token) {
  return `${API_TOKEN_PREFIX}…${token?.hint ?? ""}`;
}

/**
 * Shell snippet that points a training script at this server with a
 * personal token. Uses the placeholder until a fresh token is available.
 * @param {string} serverUrl
 * @param {string | null} token
 * @returns {string}
 */
export function tokenUsageSnippet(serverUrl, token) {
  const value = token || `${API_TOKEN_PREFIX}...`;
  return [
    `export TRACKIO_SERVER_URL=${serverUrl}`,
    `export TRACKIO_WRITE_TOKEN=${value}`,
  ].join("\n");
}

/**
 * Base URL of the dashboard the browser is on, without a trailing slash.
 * @param {{origin: string}} location
 * @param {string} [base]
 * @returns {string}
 */
export function dashboardServerUrl(location, base = "") {
  return `${location.origin}${base}`.replace(/\/+$/, "");
}
