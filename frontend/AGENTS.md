<!-- LOVABLE:BEGIN -->

> [!IMPORTANT]
> This project is connected to [Lovable](https://lovable.dev). Avoid rewriting
> published git history — force pushing, or rebasing/amending/squashing commits
> that are already pushed — as it rewrites history on Lovable's side and the
> user will likely lose their project history.
>
> Commits you push to the connected branch sync back to Lovable and show up in
> the editor, so keep the branch in a working state.

## What Lovable manages

Rules outside this block are the project's own. Change the pieces below in
Lovable, not by hand. With the [Lovable MCP](https://mcp.lovable.dev)
connected, `send_message` asks Lovable to do it; otherwise ask the user to
use the editor.

- **Database.** Do not add or edit `supabase/migrations/` or `drizzle/`.
  Ask Lovable to change the schema.
- **Generated files.** Do not edit a file whose header says it is automatically
  generated.
- **AI gateway.** Keep model calls on Lovable's gateway, and keep
  `LOVABLE_API_KEY` out of browser code.
- **Connectors.** Lovable provides native connectors. `list_connectors` shows
  which are enabled; `add_connector` only returns the dashboard link. When a
  connector is enabled, calls go through the connector gateway and need
  `LOVABLE_API_KEY`. When Lovable does not provide one, users can bring their
  own key and store it in Secrets.
- **Secrets.** Lovable manages them. Do not put secret values in the repo.

<!-- LOVABLE:END -->

## Project structure

- Screens live in `src/components/pages/*Page.tsx`; route files in `src/routes/` stay thin (head metadata + render). Why: keeps large converted layouts out of route modules so code-splitting stays simple.
- Studio screens render inside `AppShell` (`src/components/layout/AppShell.tsx`, fixed sidebar + top bar); the auth screen is full-bleed without it. Why: one shared nav with router-driven active state.
- Design tokens mirror the Material 3 (Stitch) token names (`surface-container-*`, `on-surface`, `primary-fixed`, `text-body-md`, `p-space-md`, ...) in `src/styles.css`; shadcn variables alias onto them. Why: page markup uses those utility names directly.
- Interactions are client-side simulations (no backend yet); sign-in does not authenticate. Why: the brief was UI-only.

- Shared sidebar, header, and content offsets use `--studio-sidebar-width` with explicit CSS variable utilities; one responsive width keeps navigation from covering content.
- Dropdowns use the shared `Dropdown` (`src/components/studio/Dropdown.tsx`, Radix Select) instead of native `<select>`. Why: native menus can't match the studio theme.
- Form rules that matter to users (e.g. password strength) live as pure functions in `src/lib/*` with vitest tests. Why: keeps rules testable apart from markup.
