/**
 * The patient page's own words (M4-P5, spec R19). Everything about the prescription comes from
 * the API already in the page's language; these are only the page's frame: the challenge, the
 * errors, the language switch. Hindi to be reviewed with the phrasebook (L-07).
 */

export type PageLanguage = "en" | "hi";

export interface PageStrings {
  readonly title: string;
  readonly from: (clinic: string) => string;
  readonly challengeHeading: string;
  readonly challengeHelp: string;
  readonly last4Label: string;
  readonly open: string;
  readonly wrong: (left: number | undefined) => string;
  readonly locked: string;
  readonly rateLimited: string;
  readonly unavailable: string;
  readonly invalid: string;
  readonly expired: string;
  readonly revoked: string;
  readonly switchTo: string;
  readonly askDoctor: string;
}

const EN: PageStrings = {
  title: "Your prescription",
  from: (clinic) => `From ${clinic}`,
  challengeHeading: "Confirm it is you",
  challengeHelp: "Enter the last 4 digits of the phone number the clinic has for you.",
  last4Label: "Last 4 digits of your phone number",
  open: "Show my prescription",
  wrong: (left) =>
    left === undefined ? "Those digits don't match." : `Those digits don't match. ${left} ${left === 1 ? "try" : "tries"} left.`,
  locked: "Too many attempts. Please contact the clinic to open this link again.",
  rateLimited: "Too many requests. Please wait a minute and try again.",
  unavailable: "We couldn't load this page. Please try again in a moment.",
  invalid: "This link isn't valid. Please check it, or ask the clinic for a new one.",
  expired: "This link has expired. Please ask the clinic for a new one.",
  revoked: "This link is no longer active. Please ask the clinic for a new one.",
  switchTo: "हिन्दी में देखें",
  askDoctor: "If anything here is unclear, ask your doctor or the clinic.",
};

const HI: PageStrings = {
  title: "आपका पर्चा",
  from: (clinic) => `${clinic} से`,
  challengeHeading: "पुष्टि करें कि यह आप हैं",
  challengeHelp: "क्लिनिक के पास जो फ़ोन नंबर है, उसके आख़िरी 4 अंक लिखें।",
  last4Label: "आपके फ़ोन नंबर के आख़िरी 4 अंक",
  open: "मेरा पर्चा दिखाएँ",
  wrong: (left) =>
    left === undefined ? "ये अंक मेल नहीं खाते।" : `ये अंक मेल नहीं खाते। ${left} बार और कोशिश कर सकते हैं।`,
  locked: "बहुत ज़्यादा कोशिशें हुईं। यह लिंक फिर से खुलवाने के लिए क्लिनिक से संपर्क करें।",
  rateLimited: "बहुत ज़्यादा अनुरोध। एक मिनट रुककर फिर कोशिश करें।",
  unavailable: "यह पेज अभी नहीं खुल सका। थोड़ी देर बाद फिर कोशिश करें।",
  invalid: "यह लिंक सही नहीं है। इसे जाँचें, या क्लिनिक से नया लिंक माँगें।",
  expired: "इस लिंक की समय-सीमा ख़त्म हो गई है। क्लिनिक से नया लिंक माँगें।",
  revoked: "यह लिंक अब काम नहीं करता। क्लिनिक से नया लिंक माँगें।",
  switchTo: "View in English",
  askDoctor: "कुछ भी समझ न आए तो अपने डॉक्टर या क्लिनिक से पूछें।",
};

export function stringsFor(language: PageLanguage): PageStrings {
  return language === "hi" ? HI : EN;
}

export function pageLanguage(value: string | string[] | undefined): PageLanguage | undefined {
  return value === "en" || value === "hi" ? value : undefined;
}

export function otherLanguage(language: PageLanguage): PageLanguage {
  return language === "hi" ? "en" : "hi";
}
