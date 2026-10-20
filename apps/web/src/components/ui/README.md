# components/ui — the MediEase design system (M6-P1)

Small primitives of our own, styled with the tokens in `src/app/globals.css` (`@theme`: the teal
`brand-*` shades, `canvas`, `rounded-card`, `shadow-card`, the system font stack).

| Primitive | Use |
|---|---|
| `Button`, `buttonClasses` | Actions; `buttonClasses()` styles a `Link` the same way |
| `Card` | A surface for one topic; with `title` it is a labelled region |
| `StatTile` | One number and its label; with `href` the tile links to the screen it summarises |
| `StatusBadge`, `TONES` | A status in words with one accent per status (never colour alone) |
| `PageHeader` | The page's `h1`, a line under it and its actions |
| `EmptyState` | Nothing to show yet, and the next step |
| `Skeleton` | A loading placeholder (decorative; pair it with a `role="status"` text) |
| `Tabs` | Tabs on `@radix-ui/react-tabs` (keyboard and ARIA from Radix, look ours) |
| `MotionProvider`, `m`, `STAGGER`, `RISE` | Motion (`motion/react`) through `LazyMotion`, honouring reduced motion |

Rules:

- A headless primitive is adopted only where its keyboard and screen-reader behaviour is worth
  not re-implementing (developer's amendment to decision 2), one component at a time, named in
  the phase's design. Today that is Tabs. Dialogs and drawers stay on the native `<dialog>`
  (`../Drawer.tsx`, `../Dialog.tsx`).
- Motion runs inside `MotionProvider` only (the clinic and ops shells). Use `m.*`, never
  `motion.*` (`strict` refuses it). Never on the patient pages (`/p/…`, NFR-02's 200 KB budget).
- Every interactive target is at least 24 px; status is in words as well as colour (WCAG 2.1 AA).
