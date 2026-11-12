/**
 * M7e-E1: the words of the installable app's prompts, in English and Hindi (patients choose;
 * staff screens are English).
 */

export type PwaLanguage = "en" | "hi";

export interface PwaWords {
  /** The X in the corner of an offer: closes it and does not offer again. */
  readonly close: string;
  readonly install: {
    readonly title: string;
    readonly body: string;
    readonly action: string;
    readonly later: string;
  };
  readonly ios: {
    readonly title: string;
    readonly steps: readonly string[];
    readonly done: string;
  };
  readonly update: {
    readonly body: string;
    readonly action: string;
  };
}

const EN: PwaWords = {
  close: "Close",
  install: {
    title: "Install the MediEase app",
    body: "Open MediEase from your home screen, like any other app.",
    action: "Install",
    later: "Not now",
  },
  ios: {
    title: "Add MediEase to your Home Screen",
    steps: ["Tap the Share button in Safari.", "Choose Add to Home Screen.", "Open MediEase from its new icon."],
    done: "Got it",
  },
  update: {
    body: "A new version of MediEase is ready.",
    action: "Update",
  },
};

const HI: PwaWords = {
  close: "बंद करें",
  install: {
    title: "MediEase ऐप इंस्टॉल करें",
    body: "किसी भी दूसरे ऐप की तरह, MediEase को अपनी होम स्क्रीन से खोलें।",
    action: "इंस्टॉल करें",
    later: "अभी नहीं",
  },
  ios: {
    title: "MediEase को होम स्क्रीन पर जोड़ें",
    steps: ["Safari में शेयर बटन दबाएँ।", "Add to Home Screen चुनें।", "नए आइकन से MediEase खोलें।"],
    done: "ठीक है",
  },
  update: {
    body: "MediEase का नया संस्करण तैयार है।",
    action: "अपडेट करें",
  },
};

export function pwaWords(language: PwaLanguage): PwaWords {
  return language === "hi" ? HI : EN;
}
