/**
 * Words for directory search (`/find`, M6c-P6; FR-DIS-01, 02). English and Hindi, as the rest of
 * the patient side (ADR-0015). Specialty and language names are shown as the API lists them.
 */

import type { PortalLanguage } from "./portal";

export interface FindWords {
  readonly title: string;
  readonly intro: string;
  readonly what: string;
  readonly whatHint: string;
  readonly where: string;
  readonly whereHint: string;
  readonly specialty: string;
  readonly language: string;
  readonly any: string;
  readonly available: string;
  readonly search: string;
  readonly doctors: string;
  readonly clinics: string;
  readonly showing: string;
  readonly none: string;
  readonly failed: string;
  readonly tooMany: string;
  readonly badFilter: string;
  readonly freeFrom: (day: string) => string;
  readonly noFreeTime: string;
  readonly fee: (rupees: string) => string;
  readonly speaks: string;
  readonly viewProfile: string;
  readonly viewClinic: string;
  readonly emergency: string;
  readonly switchTo: string;
  readonly switchLabel: string;
  readonly applyCta: string;
}

const EN: FindWords = {
  title: "Find a doctor",
  intro: "Clinics and doctors on MediEase. MediEase has checked every doctor's registration.",
  what: "Doctor, clinic or specialty",
  whatHint: "For example a doctor's name, a clinic's name or a specialty.",
  where: "City or PIN code",
  whereHint: "We show the same PIN first, then the same city and the nearby PIN area.",
  specialty: "Specialty",
  language: "Language",
  any: "Any",
  available: "Free in the next 7 days",
  search: "Search",
  doctors: "Doctors",
  clinics: "Clinics",
  showing: "Results",
  none: "Nothing matches yet. Try fewer words or another place.",
  failed: "Search is not working right now. Please try again.",
  tooMany: "Too many searches. Please wait a minute and try again.",
  badFilter: "Please check the PIN code: it has six digits.",
  freeFrom: (day) => `Free from ${day}`,
  noFreeTime: "No free time in the next 7 days",
  fee: (rupees) => `Fee ₹${rupees}`,
  speaks: "Speaks",
  viewProfile: "See profile and times",
  viewClinic: "See clinic and times",
  emergency: "Not for emergencies. In an emergency call your local emergency number or go to the nearest hospital.",
  switchTo: "हिंदी में देखें",
  switchLabel: "View this page in Hindi",
  applyCta: "Are you a doctor? Apply to join MediEase",
};

const HI: FindWords = {
  title: "डॉक्टर खोजें",
  intro: "MediEase पर क्लिनिक और डॉक्टर। MediEase ने हर डॉक्टर का पंजीकरण जाँचा है।",
  what: "डॉक्टर, क्लिनिक या विशेषज्ञता",
  whatHint: "जैसे डॉक्टर का नाम, क्लिनिक का नाम या विशेषज्ञता।",
  where: "शहर या पिन कोड",
  whereHint: "पहले वही पिन, फिर वही शहर और आस-पास का पिन क्षेत्र।",
  specialty: "विशेषज्ञता",
  language: "भाषा",
  any: "कोई भी",
  available: "अगले 7 दिनों में खाली समय",
  search: "खोजें",
  doctors: "डॉक्टर",
  clinics: "क्लिनिक",
  showing: "नतीजे",
  none: "अभी कुछ नहीं मिला। कम शब्द या कोई और जगह आज़माएँ।",
  failed: "खोज अभी काम नहीं कर रही है। कृपया फिर कोशिश करें।",
  tooMany: "बहुत ज़्यादा खोजें। एक मिनट रुककर फिर कोशिश करें।",
  badFilter: "कृपया पिन कोड जाँचें: उसमें छह अंक होते हैं।",
  freeFrom: (day) => `${day} से खाली`,
  noFreeTime: "अगले 7 दिनों में कोई खाली समय नहीं",
  fee: (rupees) => `शुल्क ₹${rupees}`,
  speaks: "भाषाएँ",
  viewProfile: "प्रोफ़ाइल और समय देखें",
  viewClinic: "क्लिनिक और समय देखें",
  emergency: "आपात स्थिति के लिए नहीं। आपात स्थिति में अपने यहाँ का आपातकालीन नंबर मिलाएँ या सबसे नज़दीकी अस्पताल जाएँ।",
  switchTo: "View in English",
  switchLabel: "इस पेज को अंग्रेज़ी में देखें",
  applyCta: "क्या आप डॉक्टर हैं? MediEase से जुड़ने के लिए आवेदन करें",
};

export function findWords(language: PortalLanguage): FindWords {
  return language === "hi" ? HI : EN;
}

/** "Tue 28 Oct" for a clinic-local date (YYYY-MM-DD), in the page's language. */
export function shortDay(isoDate: string, language: PortalLanguage): string {
  const day = new Date(`${isoDate}T00:00:00Z`);
  return new Intl.DateTimeFormat(language === "hi" ? "hi-IN" : "en-IN", {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  }).format(day);
}
