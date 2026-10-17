# components

Shared, feature-agnostic UI pieces used by more than one feature: `TextField` (a labelled input
with its hint and error), `useFocusOnError` (focus the first invalid field or the alert after a
failed submit) and `Drawer` (a side panel on a native `<dialog>`: focus kept inside, Escape
closes, focus returns to the opener). Feature-specific UI stays in `src/features/<feature>/`.
