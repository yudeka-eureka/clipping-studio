import { describe, expect, it } from "vitest";

import {
  STANDARD_RETENTION_HOURS,
  STORAGE_PROVIDERS,
  canCustomizeRetention,
  canRefreshVersions,
  keyProviderFor,
  maskApiKey,
  versionsFor,
  validatePasswordChange,
} from "@/lib/settings";

describe("API key shown for the chosen hook provider", () => {
  it("Gemini shows the Gemini key", () => {
    expect(keyProviderFor("gemini")).toBe("gemini");
  });
  it("OpenAI shows the OpenAI key", () => {
    expect(keyProviderFor("openai")).toBe("openai");
  });
  it("Anthropic shows the Anthropic key", () => {
    expect(keyProviderFor("anthropic")).toBe("anthropic");
  });
  it("ClipAI local needs no key", () => {
    expect(keyProviderFor("clipai")).toBeNull();
  });
});

describe("model versions", () => {
  it("checking versions needs the provider's key", () => {
    expect(canRefreshVersions("openai", "")).toBe(false);
    expect(canRefreshVersions("openai", "sk-proj-1")).toBe(true);
  });
  it("ClipAI versions can be checked without a key", () => {
    expect(canRefreshVersions("clipai", "")).toBe(true);
  });
  it("newer versions appear only after checking", () => {
    expect(versionsFor("gemini", false).map((v) => v.id)).not.toContain("gemini-2.5-pro");
    expect(versionsFor("gemini", true).map((v) => v.id)).toContain("gemini-2.5-pro");
  });
  it("saved keys show only the last 4 characters", () => {
    expect(maskApiKey("sk-proj-abcd1234")).toBe("••••••••1234");
  });
});

describe("cloud storage", () => {
  it("Cloudinary asks for cloud name, API key and API secret", () => {
    expect(STORAGE_PROVIDERS.cloudinary.fields.map((f) => f.label)).toEqual([
      "Cloud Name",
      "API Key",
      "API Secret",
    ]);
  });
  it("R2 asks for 5 fields", () => {
    expect(STORAGE_PROVIDERS.r2.fields.map((f) => f.label)).toEqual([
      "Account ID",
      "Bucket Name",
      "Access Key ID",
      "Secret Access Key",
      "Public Bucket URL",
    ]);
  });
  it("standard storage keeps files 4 hours and has no settings", () => {
    expect(STANDARD_RETENTION_HOURS).toBe(4);
    expect(STORAGE_PROVIDERS.standard.fields).toHaveLength(0);
    expect(canCustomizeRetention("standard")).toBe(false);
  });
  it("retention is customisable on Cloudinary and R2", () => {
    expect(canCustomizeRetention("cloudinary")).toBe(true);
    expect(canCustomizeRetention("r2")).toBe(true);
  });
});

describe("change password", () => {
  const ok = { current: "OldPass1!", next: "NewPass2@", confirm: "NewPass2@" };
  it("accepts a valid change", () => {
    expect(validatePasswordChange(ok)).toEqual({});
  });
  it("requires the old password", () => {
    expect(validatePasswordChange({ ...ok, current: "" }).current).toBeDefined();
  });
  it("new password needs 8+ characters", () => {
    expect(validatePasswordChange({ ...ok, next: "Ab1!", confirm: "Ab1!" }).next).toBeDefined();
  });
  it("new password needs a number and a symbol", () => {
    expect(
      validatePasswordChange({ ...ok, next: "abcdefgh!", confirm: "abcdefgh!" }).next,
    ).toBeDefined();
    expect(
      validatePasswordChange({ ...ok, next: "abcdefgh1", confirm: "abcdefgh1" }).next,
    ).toBeDefined();
  });
  it("new password must differ from the old one", () => {
    expect(
      validatePasswordChange({ ...ok, next: ok.current, confirm: ok.current }).next,
    ).toBeDefined();
  });
  it("confirmation must match the new password", () => {
    expect(validatePasswordChange({ ...ok, confirm: "NewPass2#" }).confirm).toBeDefined();
  });
});
