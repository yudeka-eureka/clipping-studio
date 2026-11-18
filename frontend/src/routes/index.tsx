import { createFileRoute } from "@tanstack/react-router";
import { LandingPage } from "@/components/pages/LandingPage";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Clipping Studio \u2014 Dari video panjang ke klip untuk ditinjau" },
      {
        name: "description",
        content:
          "Masukkan video, dapatkan kandidat klip berbantuan AI untuk meninjau dan merender hasilnya di satu workspace.",
      },
      {
        property: "og:title",
        content: "Clipping Studio \u2014 Dari video panjang ke klip untuk ditinjau",
      },
      {
        property: "og:description",
        content:
          "Masukkan video, dapatkan kandidat klip berbantuan AI untuk meninjau dan merender hasilnya di satu workspace.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: LandingPage,
});
