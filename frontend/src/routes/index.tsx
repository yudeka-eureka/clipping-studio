import { createFileRoute } from "@tanstack/react-router";
import { LandingPage } from "@/components/pages/LandingPage";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Clipping Studio \u2014 Dari video panjang ke klip untuk ditinjau" },
      {
        name: "description",
        content:
          "Workspace lokal untuk menemukan momen klip dengan Gemini, Claude, atau ChatGPT, lalu meninjau dan merender hasilnya.",
      },
      {
        property: "og:title",
        content: "Clipping Studio \u2014 Dari video panjang ke klip untuk ditinjau",
      },
      {
        property: "og:description",
        content:
          "Workspace lokal untuk menemukan momen klip dengan Gemini, Claude, atau ChatGPT, lalu meninjau dan merender hasilnya.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: LandingPage,
});
