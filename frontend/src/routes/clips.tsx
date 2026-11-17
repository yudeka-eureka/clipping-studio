import { createFileRoute, redirect } from "@tanstack/react-router";

export const Route = createFileRoute("/clips")({
  beforeLoad: () => {
    throw redirect({ to: "/app/clips" });
  },
});
