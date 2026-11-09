# components/ui — the MediEase design system

The system is documented in the repository's `DESIGN.md` (M7c-P7). Tokens are CSS variables in
`src/app/globals.css` (`@theme`): the brand scale on `#147D72`, the retuned neutrals, semantic
colours (`surface`, `line`, `ink`, `success`, `warning`, `danger`, `info`), radius, shadows,
`ease-brand`, and the named text styles (`heading-1` … `caption-5`). The font is Manrope,
self-hosted, on every surface except patient pages (system font there, 200 KB budget). Browse
every component at `/design-system`.

| Primitive | Use |
|---|---|
| `Button`, `buttonClasses` | Actions; `loading` keeps the label and blocks a second click; `buttonClasses()` styles a `Link` |
| `Card` | A surface for one topic; with `title` it is a labelled region |
| `StatTile` | One number and its label; with `href` the tile links to the screen it summarises |
| `StatusBadge`, `TONES` | A status in words with one accent per status (never colour alone) |
| `Alert` | A message inside the page: info, success, warning, danger |
| `Toast` | `ToastProvider` and `useToast()`: confirmations of finished actions only, never errors |
| `Tooltip` | Extra detail on hover and focus; never the only place for information |
| `PageHeader`, `Breadcrumbs` | The page's `h1`, its line and actions; the way back on nested screens |
| `Pagination` | Previous and next with "Page 2 of 7" |
| `EmptyState` | Nothing to show yet, and the next step |
| `Skeleton`, `Spinner` | Loading: skeletons for content, a spinner only inside a button |
| `Avatar`, `KeyValue` | Initials beside a name; a record's label and value pairs |
| `Logo`, `Emblem` | The MediEase logo as inline SVG (never redraw the mark by hand) |
| `Tabs` | Tabs on `@radix-ui/react-tabs` |
| `MotionProvider`, `m`, `STAGGER`, `RISE`, `LayoutMotion` | Motion, inside `MotionProvider` only |
| `Field`: `TextField`, `SelectField`, `TextAreaField`, `CheckboxField`, `DateField`, `TimeField`, `ErrorSummary` | Form controls sharing label, hint, error and `aria-describedby` |
| `table`: `TABLE`, `TABLE_WRAP`, `TH`, `TR`, `TD` | A table from 768 px, cards below, from one markup |
| `AuthFrame` | The centred card of sign-in, invitations and the clinic chooser |
| `cx` | Joins classes; it does not resolve conflicts, so a component lists the caller's `className` last |

Rules:

- A headless primitive is adopted only where its keyboard and screen-reader behaviour is worth
  not re-implementing: Tabs, Toast, Tooltip (Radix). Dialogs and drawers stay on the native
  `<dialog>` (`../Dialog.tsx`, `../Drawer.tsx`, `../ConfirmDialog.tsx`).
- Motion runs inside `MotionProvider` only (the clinic and ops `Shell`), with `m.*`. Never on
  patient pages (200 KB budget); there, CSS transitions with `ease-brand`.
- Every interactive target is at least 24 px; status is in words as well as colour (WCAG 2.1 AA).
- Icons are `lucide-react`, imported one by one, always `aria-hidden` beside words.
