import { QueryClient } from "@tanstack/react-query";
import { createRouter, rootRouteId } from "@tanstack/react-router";
import { describe, expect, it } from "vitest";

import { routeTree } from "@/routeTree.gen";
import { Route as LandingRoute } from "@/routes/index";

describe("App routing", () => {
  const router = createRouter({ routeTree, context: { queryClient: new QueryClient() } });

  it("matches a page for / (Landing Page) instead of falling back to not found", () => {
    const matches = router.matchRoutes("/");
    expect(matches.at(-1)?.routeId).not.toBe(rootRouteId);
    expect(matches.some((m) => m.routeId === "/")).toBe(true);
  });

  it("describes the landing page without promising publishing outcomes", () => {
    const head = LandingRoute.options.head?.({} as never) as { meta?: Array<Record<string, string>> };
    const title = head.meta?.find((meta) => meta.title)?.title;
    const description = head.meta?.find((meta) => meta.name === "description")?.content;

    expect(title).toBe("Clipping Studio — Dari video panjang ke klip untuk ditinjau");
    expect(description).toContain("meninjau");
    expect(description).not.toMatch(/viral|siap posting/i);
  });

  it("matches a page for /app (Studio) route group", () => {
    const matches = router.matchRoutes("/app");
    expect(matches.at(-1)?.routeId).not.toBe(rootRouteId);
    expect(matches.some((m) => m.routeId === "/app" || m.routeId === "/app/")).toBe(true);
  });

  it("matches a page for /app/clips", () => {
    const matches = router.matchRoutes("/app/clips");
    expect(matches.at(-1)?.routeId).not.toBe(rootRouteId);
    expect(matches.some((m) => m.routeId === "/app/clips")).toBe(true);
  });

  it("matches a page for /app/settings", () => {
    const matches = router.matchRoutes("/app/settings");
    expect(matches.at(-1)?.routeId).not.toBe(rootRouteId);
    expect(matches.some((m) => m.routeId === "/app/settings")).toBe(true);
  });

  it("matches a page for /auth", () => {
    const matches = router.matchRoutes("/auth");
    expect(matches.at(-1)?.routeId).not.toBe(rootRouteId);
    expect(matches.some((m) => m.routeId === "/auth")).toBe(true);
  });
});
