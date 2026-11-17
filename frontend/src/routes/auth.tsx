import { createFileRoute } from "@tanstack/react-router";

import { AuthPage } from "@/components/pages/AuthPage";

export const Route = createFileRoute("/auth")({
  head: () => ({
    meta: [
      { title: "Sign In or Create Account \u2014 Clipping Studio" },
      {
        name: "description",
        content:
          "Sign in or create your Clipping Studio account to turn long-form videos into viral clips.",
      },
      { property: "og:title", content: "Sign In or Create Account \u2014 Clipping Studio" },
      {
        property: "og:description",
        content:
          "Sign in or create your Clipping Studio account to turn long-form videos into viral clips.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Page,
});

function Page() {
  return <AuthPage />;
}
