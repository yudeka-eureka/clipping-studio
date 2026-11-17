import { describe, it, expect, beforeEach } from "vitest";
import { getStoredToken, setStoredToken, getAnonymousSessionId, getMediaUrl, getWsUrl, apiJobs, ApiError } from "../lib/api";

describe("API Client Helper Unit Tests", () => {
  beforeEach(() => {
    if (typeof window !== "undefined" && window.localStorage) {
      window.localStorage.clear();
    }
  });

  it("stores and retrieves auth token from localStorage", () => {
    expect(getStoredToken()).toBeNull();
    setStoredToken("test-jwt-token");
    expect(getStoredToken()).toBe("test-jwt-token");
    setStoredToken(null);
    expect(getStoredToken()).toBeNull();
  });

  it("persists and retrieves anonymous session ID", () => {
    const sid1 = getAnonymousSessionId();
    expect(sid1).toBeTruthy();
    expect(sid1.length).toBeGreaterThan(10);
    const sid2 = getAnonymousSessionId();
    expect(sid2).toBe(sid1);
  });

  it("generates correct media URLs", () => {
    const url = getMediaUrl("job-123", "clips/clip-1.mp4");
    expect(url).toContain("/media/job-123/clips/clip-1.mp4");
    expect(url).toContain("session_id=");

    const empty = getMediaUrl("job-123", "");
    expect(empty).toBe("");

    const fullHttp = getMediaUrl("job-123", "https://cdn.example.com/video.mp4");
    expect(fullHttp).toBe("https://cdn.example.com/video.mp4");

    // With token
    setStoredToken("test-token-123");
    const urlWithToken = getMediaUrl("job-123", "clips/clip-1.mp4");
    expect(urlWithToken).toContain("token=test-token-123");
    expect(urlWithToken).toContain("session_id=");
    setStoredToken(null);
  });

  it("derives valid WebSocket URL", () => {
    const wsUrl = getWsUrl();
    expect(wsUrl).toMatch(/^wss?:\/\//);
    expect(wsUrl).toContain("/ws");
    expect(wsUrl).toContain("session_id=");

    // With token
    setStoredToken("jwt-token-abc");
    const wsUrlWithToken = getWsUrl();
    expect(wsUrlWithToken).toContain("token=jwt-token-abc");
    expect(wsUrlWithToken).toContain("session_id=");
    setStoredToken(null);
  });

  it("appends auth token and session_id to download all URL", () => {
    const url = apiJobs.getDownloadAllUrl("job-123");
    expect(url).toContain("/api/jobs/job-123/download-all");
    expect(url).toContain("session_id=");

    setStoredToken("dl-token-xyz");
    const urlWithToken = apiJobs.getDownloadAllUrl("job-123");
    expect(urlWithToken).toContain("token=dl-token-xyz");
    expect(urlWithToken).toContain("session_id=");
    setStoredToken(null);
  });

  it("creates ApiError instances with proper status and message", () => {
    const err = new ApiError(400, "Validation failed", { field: "username" });
    expect(err.name).toBe("ApiError");
    expect(err.status).toBe(400);
    expect(err.message).toBe("Validation failed");
    expect(err.detail).toEqual({ field: "username" });
  });
});
