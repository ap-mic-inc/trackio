export function alertDismissAccess(mutationStatus) {
  const status = mutationStatus || {};
  if (status.auth === "static") {
    return { visible: false, allowed: false, reason: null };
  }
  if (status.allowed) {
    return { visible: true, allowed: true, reason: null };
  }
  let reason;
  if (status.spaces) {
    reason = "Sign in with Hugging Face (write access) to dismiss alerts";
  } else if (status.oidcEnabled || status.auth === "oidc_insufficient") {
    reason = "Sign in with an account that has write access to dismiss alerts";
  } else {
    reason =
      "Open the dashboard with its write-access link (?write_token=…) to dismiss alerts";
  }
  return { visible: true, allowed: false, reason };
}
