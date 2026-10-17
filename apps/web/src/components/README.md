# components

Shared, feature-agnostic UI pieces used by more than one feature: `TextField` (a labelled input
with its hint and error), `useFocusOnError` (focus the first invalid field or the alert after a
failed submit), `Drawer` (a side panel on a native `<dialog>`: focus kept inside, Escape
closes, focus returns to the opener), `Dialog` (the same as a centred modal, for confirmations and
short forms), `Menu` (a WAI-ARIA menu button) and `useNow` (the current time, refreshed every
minute, because React's purity rule forbids reading the clock during render). In `Drawer` and
`Dialog`, mark the field where the person starts with `data-autofocus`: it takes the focus once
the dialog is open (a child's own `focus()` in its effect runs too early). Feature-specific UI
stays in `src/features/<feature>/`.
