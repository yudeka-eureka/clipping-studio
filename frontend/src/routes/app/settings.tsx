import { createFileRoute } from "@tanstack/react-router";
import { SettingsPage } from "@/components/pages/SettingsPage";

export const Route = createFileRoute("/app/settings")({
  head: () => ({
    meta: [
      { title: "Studio Settings & Preferences \u2014 Clipping Studio" },
      {
        name: "description",
        content:
          "Manage your creator profile, AI model API keys, and default pipeline configurations.",
      },
      { property: "og:title", content: "Studio Settings & Preferences \u2014 Clipping Studio" },
      {
        property: "og:description",
        content:
          "Manage your creator profile, AI model API keys, and default pipeline configurations.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Page,
});

function Page() {
  return <SettingsPage />;
}
