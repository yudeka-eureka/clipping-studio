import { createFileRoute } from "@tanstack/react-router";
import { ClipsPage } from "@/components/pages/ClipsPage";

export const Route = createFileRoute("/app/clips")({
  head: () => ({
    meta: [
      { title: "Clip Results & AI Output Monitor \u2014 Clipping Studio" },
      {
        name: "description",
        content:
          "Review AI-generated vertical clips, synced transcripts, virality scores, and customize captions.",
      },
      { property: "og:title", content: "Clip Results & AI Output Monitor \u2014 Clipping Studio" },
      {
        property: "og:description",
        content:
          "Review AI-generated vertical clips, synced transcripts, virality scores, and customize captions.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Page,
});

function Page() {
  return <ClipsPage />;
}
