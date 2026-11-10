/**
 * M7c-P7 (M8): the consultation screen's card frame and heading, shared by the notes, the
 * prescription, the issued card, earlier visits and addenda so they read as one set.
 */
export const CARD = "space-y-4 rounded-card border border-line bg-white p-4 shadow-card sm:p-5";
export const CARD_TITLE = "flex items-center gap-2 text-lg font-bold text-slate-900";

/** The autosave line ("Saved", "Saving…") as a quiet pill beside a card's heading. */
export const SAVE_PILL = "inline-flex min-h-7 items-center gap-1.5 rounded-full bg-slate-100 px-2.5 text-sm text-slate-700";

/** The amber "stale" box with *Reload*, which every autosaving card shows the same way. */
export const STALE_BOX = "space-y-2 rounded-lg border border-warning-line bg-warning-soft p-3 text-slate-900";
