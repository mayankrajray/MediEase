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
| `LayoutMotion`, `LIST_ITEM` | Lists whose items glide to a new place and rise in when new (layout features load on first use, M6-P2) |
| `Field`: `TextField`, `SelectField`, `TextAreaField`, `CheckboxField`; `INPUT`, `LABEL`, `HINT` | Form controls sharing label, hint, error and `aria-describedby`; 40 px tall (M6-P2) |
| `table`: `TABLE`, `TABLE_WRAP`, `TH`, `TR`, `TD` | A table from 768 px, cards below, from one markup: every `td` has `data-label`; keep the explicit ARIA roles (M6-P2) |
| `AuthFrame` | The centred card of sign-in, invitations and the clinic chooser (M6-P2) |

Rules:

- A headless primitive is adopted only where its keyboard and screen-reader behaviour is worth
  not re-implementing (developer's amendment to decision 2), one component at a time, named in
  the phase's design. Today that is Tabs. Dialogs and drawers stay on the native `<dialog>`
  (`../Drawer.tsx`, `../Dialog.tsx`).
- Motion runs inside `MotionProvider` only (the shared `Shell` of the clinic and ops screens). Use
  `m.*`, never `motion.*` (`strict` refuses it). Never on the patient pages (`/p/…`, NFR-02's
  200 KB budget). Drawers and dialogs animate with CSS (`.me-overlay` in `globals.css`), not
  Motion, so they stay native `<dialog>`s.
- Every interactive target is at least 24 px; status is in words as well as colour (WCAG 2.1 AA).
