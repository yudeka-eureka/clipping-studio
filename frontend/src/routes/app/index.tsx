import { createFileRoute } from "@tanstack/react-router";
import { UploadPage } from "@/components/pages/UploadPage";

export const Route = createFileRoute("/app/")({
  head: () => ({
    meta: [
      { title: "Upload & Source Setup \u2014 Clipping Studio" },
      {
        name: "description",
        content:
          "Upload long-form footage, pick a target platform, and tune AI reframing and caption presets.",
      },
      { property: "og:title", content: "Upload & Source Setup \u2014 Clipping Studio" },
      {
        property: "og:description",
        content:
          "Upload long-form footage, pick a target platform, and tune AI reframing and caption presets.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Page,
});

function Page() {
  return <UploadPage />;
}
