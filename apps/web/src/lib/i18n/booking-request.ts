/**
 * Words for the public clinic page (`/c/{slug}`) and the request form (M6b-P4; FR-PUB-01, 02,
 * FR-PRT-08). English and Hindi, as the rest of the patient side (ADR-0015). Times come from the
 * portal's formatters, on the clinic's clock.
 */

import { parsePortalLanguage, type PortalLanguage } from "./portal";

export interface BookingWords {
  readonly lang: PortalLanguage;
  readonly switchTo: string;
  readonly switchLabel: string;
  readonly page: {
    readonly doctors: string;
    readonly hours: string;
    readonly weekdays: readonly string[];
    readonly call: string;
    readonly directions: string;
    readonly share: string;
    readonly copy: string;
    readonly copied: string;
    readonly emergency: string;
    readonly howItWorks: string;
    readonly pickDoctor: string;
    readonly seeTimes: string;
    readonly timesFor: (doctor: string) => string;
    readonly loading: string;
    readonly none: string;
    readonly failed: string;
    readonly retry: string;
    readonly placesLeft: (n: number) => string;
    readonly session: (from: string, to: string) => string;
    readonly requestSession: string;
    readonly requestSlot: (time: string) => string;
    // M6c-P5 (FR-DIS-03): the published profile.
    readonly specialties: string;
    readonly languages: string;
    readonly fee: (rupees: string) => string;
    readonly profile: string;
    readonly allDoctors: string;
  };
  readonly form: {
    readonly title: string;
    readonly summary: (doctor: string, clinic: string, when: string) => string;
    readonly notAvailable: string;
    readonly chooseAnother: string;
    readonly phone: string;
    readonly phoneHelp: string;
    readonly age: string;
    readonly sex: string;
    readonly optional: string;
    readonly sexes: Readonly<Record<"FEMALE" | "MALE" | "OTHER" | "UNDISCLOSED", string>>;
    readonly choose: string;
    readonly reason: string;
    readonly reasonHelp: string;
    readonly ack: string;
    readonly submit: string;
    readonly sending: string;
    readonly holdNote: string;
    readonly doneTitle: string;
    readonly doneBody: (when: string) => string;
    readonly goAppointments: string;
    readonly verify: string;
    readonly goAccount: string;
    readonly errors: Readonly<Record<string, string>>;
    readonly rateLimited: (seconds: string | undefined) => string;
  };
  readonly mine: {
    readonly title: string;
    readonly requested: string;
    readonly waiting: string;
    // M6b-P5 (R49).
    readonly proposed: string;
    readonly proposedBody: (when: string, original: string) => string;
    readonly replyBy: (when: string) => string;
    readonly acceptTime: string;
    readonly noThanks: string;
    readonly accepted: string;
    readonly declinedByYou: string;
    readonly declined: string;
    readonly expired: string;
    readonly expiredBody: string;
    readonly call: string;
    readonly reasons: Readonly<Record<string, string>>;
    readonly answerFailed: string;
  };
}

const EN: BookingWords = {
  lang: "en",
  switchTo: "हिन्दी",
  switchLabel: "हिन्दी में देखें (view in Hindi)",
  page: {
    doctors: "Doctors",
    hours: "Usual hours",
    weekdays: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    call: "Call the clinic",
    directions: "Directions",
    share: "Share this page",
    copy: "Copy link",
    copied: "Link copied",
    emergency: "This page is not for emergencies. In an emergency call your local emergency number or go to the nearest hospital.",
    howItWorks: "You ask for a time and the clinic replies. A request is not a confirmed booking. A time you ask for is kept for you for a short while.",
    pickDoctor: "Choose a doctor to see the times they have free.",
    seeTimes: "See times",
    timesFor: (doctor) => `Free times with ${doctor}`,
    loading: "Loading times.",
    none: "No free times in the next 14 days. Please call the clinic.",
    failed: "We could not load the times.",
    retry: "Try again",
    placesLeft: (n) => `${n} ${n === 1 ? "place" : "places"} left`,
    session: (from, to) => `Session ${from} to ${to}`,
    requestSession: "Ask for this session",
    requestSlot: (time) => `Ask for ${time}`,
    specialties: "Specialties",
    languages: "Speaks",
    fee: (rupees) => `Consultation fee ₹${rupees}`,
    profile: "Doctor's profile",
    allDoctors: "All doctors at this clinic",
  },
  form: {
    title: "Ask for this time",
    summary: (doctor, clinic, when) => `${doctor} at ${clinic}, ${when}`,
    notAvailable: "This time is not available any more.",
    chooseAnother: "Choose another time",
    phone: "Phone number the clinic can call",
    phoneHelp: "Only the clinic sees it.",
    age: "Age in years",
    sex: "Sex",
    optional: "(optional)",
    sexes: { FEMALE: "Female", MALE: "Male", OTHER: "Other", UNDISCLOSED: "Prefer not to say" },
    choose: "Choose",
    reason: "Reason for the visit",
    reasonHelp: "A few words, up to 200 characters. Only the clinic sees it.",
    ack: "This is not an emergency.",
    submit: "Send request",
    sending: "Sending.",
    holdNote: "The clinic keeps this time for you for a short while, and will reply here.",
    doneTitle: "Requested",
    doneBody: (when) => `The clinic will reply about ${when}. It is not confirmed until they do. You can see it in My appointments.`,
    goAppointments: "Go to My appointments",
    verify: "Please confirm your email address first. We emailed you a link when you signed up.",
    goAccount: "Go to my account",
    errors: {
      APT_SLOT_TAKEN: "Someone else just asked for this time. Please choose another.",
      APT_SESSION_FULL: "This session is full. Please choose another.",
      APT_SLOT_HELD: "Someone else has asked for this time and the clinic is holding it. Please choose another, or try again later.",
      APT_SESSION_CLOSED: "The clinic is not taking requests for this session. Please choose another.",
      APT_OUTSIDE_SCHEDULE: "That is not one of the clinic's times. Please choose again.",
      PRT_REQUEST_EXISTS: "You have already asked for this session. The clinic will reply.",
      PRT_TOO_MANY_REQUESTS: "You have 5 open requests. Wait for a clinic to answer one before asking for another.",
      PRT_UNVERIFIED_ACCOUNT: "Please confirm your email address first.",
      REQ_NOT_FOUND: "We could not find this clinic or time.",
    },
    rateLimited: (seconds) =>
      seconds === undefined ? "Too many attempts. Please wait a little and try again." : `Too many attempts. Please try again in ${seconds} seconds.`,
  },
  mine: {
    title: "Requested",
    requested: "Requested",
    waiting: "Waiting for the clinic to reply",
    proposed: "Suggested another time",
    proposedBody: (when, original) => `The clinic suggests ${when} instead of ${original}.`,
    replyBy: (when) => `Please answer by ${when}.`,
    acceptTime: "Accept this time",
    noThanks: "No thanks",
    accepted: "Booked. You can see it under your clinic below.",
    declinedByYou: "You said no thanks to the suggested time.",
    declined: "Declined",
    expired: "Expired",
    expiredBody: "The clinic did not reply in time. Please call them.",
    call: "Call the clinic",
    reasons: {
      TIME_UNAVAILABLE: "That time is no longer available.",
      DOCTOR_UNAVAILABLE: "The doctor is not available then.",
      PLEASE_CALL: "Please call the clinic.",
      NOT_ONLINE: "This cannot be booked online. Please call the clinic.",
      DUPLICATE: "You already have a request or booking for this.",
      OTHER: "The clinic could not book this time.",
      PATIENT_DECLINED: "You said no thanks to the suggested time.",
      CLINIC_UNAVAILABLE: "This clinic is not taking requests on MediEase at the moment. Please call them.",
    },
    answerFailed: "This suggestion is no longer open. Please call the clinic.",
  },
};

const HI: BookingWords = {
  lang: "hi",
  switchTo: "English",
  switchLabel: "View in English (अंग्रेज़ी में देखें)",
  page: {
    doctors: "डॉक्टर",
    hours: "सामान्य समय",
    weekdays: ["सोम", "मंगल", "बुध", "गुरु", "शुक्र", "शनि", "रवि"],
    call: "क्लिनिक को फ़ोन करें",
    directions: "रास्ता देखें",
    share: "यह पेज साझा करें",
    copy: "लिंक कॉपी करें",
    copied: "लिंक कॉपी हो गया",
    emergency: "यह पेज आपात स्थिति के लिए नहीं है। आपात स्थिति में अपने यहाँ का आपातकालीन नंबर मिलाएँ या सबसे नज़दीकी अस्पताल जाएँ।",
    howItWorks: "आप समय माँगते हैं और क्लिनिक जवाब देता है। अनुरोध पक्की बुकिंग नहीं है। आपका माँगा हुआ समय थोड़ी देर आपके लिए रोका जाता है।",
    pickDoctor: "खाली समय देखने के लिए डॉक्टर चुनें।",
    seeTimes: "समय देखें",
    timesFor: (doctor) => `${doctor} के खाली समय`,
    loading: "समय लोड हो रहे हैं.",
    none: "अगले 14 दिनों में कोई खाली समय नहीं है। कृपया क्लिनिक को फ़ोन करें।",
    failed: "हम समय लोड नहीं कर सके।",
    retry: "फिर कोशिश करें",
    placesLeft: (n) => `${n} जगह बाकी`,
    session: (from, to) => `सत्र ${from} से ${to}`,
    requestSession: "इस सत्र के लिए माँगें",
    requestSlot: (time) => `${time} माँगें`,
    specialties: "विशेषज्ञता",
    languages: "भाषाएँ",
    fee: (rupees) => `परामर्श शुल्क ₹${rupees}`,
    profile: "डॉक्टर की प्रोफ़ाइल",
    allDoctors: "इस क्लिनिक के सभी डॉक्टर",
  },
  form: {
    title: "यह समय माँगें",
    summary: (doctor, clinic, when) => `${doctor}, ${clinic}, ${when}`,
    notAvailable: "यह समय अब उपलब्ध नहीं है।",
    chooseAnother: "दूसरा समय चुनें",
    phone: "फ़ोन नंबर जिस पर क्लिनिक कॉल कर सके",
    phoneHelp: "इसे सिर्फ़ क्लिनिक देखता है।",
    age: "उम्र (साल में)",
    sex: "लिंग",
    optional: "(वैकल्पिक)",
    sexes: { FEMALE: "महिला", MALE: "पुरुष", OTHER: "अन्य", UNDISCLOSED: "बताना नहीं चाहते" },
    choose: "चुनें",
    reason: "आने का कारण",
    reasonHelp: "कुछ शब्द, 200 अक्षर तक। इसे सिर्फ़ क्लिनिक देखता है।",
    ack: "यह आपात स्थिति नहीं है।",
    submit: "अनुरोध भेजें",
    sending: "भेज रहे हैं.",
    holdNote: "क्लिनिक यह समय थोड़ी देर आपके लिए रोकता है, और यहीं जवाब देगा।",
    doneTitle: "अनुरोध भेजा गया",
    doneBody: (when) => `क्लिनिक ${when} के बारे में जवाब देगा। जब तक वह जवाब नहीं देता, यह पक्का नहीं है। आप इसे मेरी अपॉइंटमेंट में देख सकते हैं।`,
    goAppointments: "मेरी अपॉइंटमेंट पर जाएँ",
    verify: "कृपया पहले अपना ईमेल पता सत्यापित करें। साइन अप करते समय हमने आपको एक लिंक भेजा था।",
    goAccount: "मेरे खाते पर जाएँ",
    errors: {
      APT_SLOT_TAKEN: "किसी और ने अभी यह समय माँगा है। कृपया दूसरा चुनें।",
      APT_SESSION_FULL: "यह सत्र भर गया है। कृपया दूसरा चुनें।",
      APT_SLOT_HELD: "किसी और ने यह समय माँगा है और क्लिनिक ने इसे रोक रखा है। कृपया दूसरा चुनें, या बाद में कोशिश करें।",
      APT_SESSION_CLOSED: "क्लिनिक इस सत्र के लिए अनुरोध नहीं ले रहा। कृपया दूसरा चुनें।",
      APT_OUTSIDE_SCHEDULE: "यह क्लिनिक के समयों में से नहीं है। कृपया फिर चुनें।",
      PRT_REQUEST_EXISTS: "आप इस सत्र के लिए पहले ही माँग चुके हैं। क्लिनिक जवाब देगा।",
      PRT_TOO_MANY_REQUESTS: "आपके 5 अनुरोध खुले हैं। नया माँगने से पहले किसी क्लिनिक के जवाब का इंतज़ार करें।",
      PRT_UNVERIFIED_ACCOUNT: "कृपया पहले अपना ईमेल पता सत्यापित करें।",
      REQ_NOT_FOUND: "हमें यह क्लिनिक या समय नहीं मिला।",
    },
    rateLimited: (seconds) =>
      seconds === undefined ? "बहुत ज़्यादा कोशिशें। कृपया थोड़ा रुककर फिर कोशिश करें।" : `बहुत ज़्यादा कोशिशें। कृपया ${seconds} सेकंड बाद फिर कोशिश करें।`,
  },
  mine: {
    title: "अनुरोध भेजे गए",
    requested: "अनुरोध भेजा गया",
    waiting: "क्लिनिक के जवाब का इंतज़ार",
    proposed: "दूसरा समय सुझाया गया",
    proposedBody: (when, original) => `क्लिनिक ${original} की जगह ${when} सुझाता है।`,
    replyBy: (when) => `कृपया ${when} तक जवाब दें।`,
    acceptTime: "यह समय स्वीकार करें",
    noThanks: "नहीं, धन्यवाद",
    accepted: "बुक हो गया। नीचे अपने क्लिनिक में देखें।",
    declinedByYou: "आपने सुझाए गए समय के लिए मना कर दिया।",
    declined: "मना किया गया",
    expired: "समय निकल गया",
    expiredBody: "क्लिनिक ने समय पर जवाब नहीं दिया। कृपया उन्हें फ़ोन करें।",
    call: "क्लिनिक को फ़ोन करें",
    reasons: {
      TIME_UNAVAILABLE: "वह समय अब उपलब्ध नहीं है।",
      DOCTOR_UNAVAILABLE: "उस समय डॉक्टर उपलब्ध नहीं हैं।",
      PLEASE_CALL: "कृपया क्लिनिक को फ़ोन करें।",
      NOT_ONLINE: "इसे ऑनलाइन बुक नहीं किया जा सकता। कृपया क्लिनिक को फ़ोन करें।",
      DUPLICATE: "इसके लिए आपका अनुरोध या बुकिंग पहले से है।",
      OTHER: "क्लिनिक यह समय बुक नहीं कर सका।",
      PATIENT_DECLINED: "आपने सुझाए गए समय के लिए मना कर दिया।",
      CLINIC_UNAVAILABLE: "यह क्लिनिक अभी MediEase पर अनुरोध नहीं ले रहा है। कृपया उन्हें फ़ोन करें।",
    },
    answerFailed: "यह सुझाव अब खुला नहीं है। कृपया क्लिनिक को फ़ोन करें।",
  },
};

export function bookingWords(language: PortalLanguage): BookingWords {
  return language === "hi" ? HI : EN;
}

/** `?lang=` wins, then the portal's language cookie, then English. */
export function pickLanguage(asked: string | string[] | undefined, cookie: string | undefined): PortalLanguage {
  const value = Array.isArray(asked) ? asked[0] : asked;
  return parsePortalLanguage(value === "hi" || value === "en" ? value : cookie);
}
