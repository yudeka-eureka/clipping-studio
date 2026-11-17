import { createFileRoute } from "@tanstack/react-router";
import { LandingPage } from "@/components/pages/LandingPage";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Clipping Studio \u2014 Dari satu video, jadi banyak momen" },
      {
        name: "description",
        content:
          "Clipping Studio membantu kreator mengubah video panjang menjadi klip pendek yang siap dipakai.",
      },
      {
        property: "og:title",
        content: "Clipping Studio \u2014 Dari satu video, jadi banyak momen",
      },
      {
        property: "og:description",
        content:
          "Clipping Studio membantu kreator mengubah video panjang menjadi klip pendek yang siap dipakai.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: LandingPage,
});
