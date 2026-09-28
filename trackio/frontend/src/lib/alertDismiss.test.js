import { describe, expect, test } from "vitest";
import { alertDismissAccess } from "./alertDismiss.js";

describe("alertDismissAccess", () => {
  test("allows dismissing with write access", () => {
    expect(alertDismissAccess({ allowed: true, auth: "local" })).toEqual({
      visible: true,
      allowed: true,
      reason: null,
    });
  });

  test("hides dismiss controls on static dashboards", () => {
    expect(alertDismissAccess({ allowed: false, auth: "static" }).visible).toBe(false);
  });

  test("explains the write token when a local dashboard is read-only", () => {
    const access = alertDismissAccess({ allowed: false, auth: "none", spaces: false });
    expect(access).toMatchObject({ visible: true, allowed: false });
    expect(access.reason).toContain("write_token");
  });

  test("asks for sign-in on Spaces and OIDC dashboards", () => {
    expect(alertDismissAccess({ allowed: false, spaces: true }).reason).toContain(
      "Hugging Face",
    );
    expect(
      alertDismissAccess({ allowed: false, auth: "oidc_insufficient" }).reason,
    ).toContain("write access");
  });

  test("treats a missing status as read-only", () => {
    expect(alertDismissAccess(undefined)).toMatchObject({ visible: true, allowed: false });
  });
});
