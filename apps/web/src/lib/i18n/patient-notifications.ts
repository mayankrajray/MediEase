/**
 * Words for the portal's notifications, their switches and the live token page (M6b-P6; spec
 * R55-R72). English and Hindi, as the rest of the patient side (ADR-0015). Notification titles
 * themselves come from the API, already in the account's language (R59).
 */

import type { components } from "@/lib/api/schema";

import type { PortalLanguage } from "./portal";

export type PatientNotificationKind = components["schemas"]["PatientNotificationKind"];
export type LiveState = components["schemas"]["LiveQueue"]["state"];

export interface NotificationWords {
  readonly bell: (unread: number) => string;
  readonly arrived: (unread: number) => string;
  readonly title: string;
  readonly empty: string;
  readonly unread: string;
  readonly markAll: string;
  readonly allRead: string;
  readonly settings: string;
  readonly switches: {
    readonly title: string;
    readonly help: string;
    readonly inApp: string;
    readonly email: string;
    readonly saved: string;
    readonly kinds: Readonly<Record<PatientNotificationKind, string>>;
  };
  readonly liveButton: string;
  readonly liveOpening: string;
}

export interface LiveWords {
  readonly lang: PortalLanguage;
  readonly switchTo: string;
  readonly switchLabel: string;
  readonly heading: string;
  readonly yourToken: (n: number) => string;
  readonly yourSlot: (time: string) => string;
  readonly ahead: (n: number) => string;
  readonly nowSeeing: (what: string) => string;
  readonly token: (n: number) => string;
  readonly nobodyYet: string;
  readonly states: Readonly<Record<LiveState, string>>;
  readonly startsAt: (time: string) => string;
  readonly updated: (time: string) => string;
  readonly refreshNote: string;
  readonly offline: string;
  readonly invalid: string;
  readonly expired: string;
  readonly unavailable: string;
  readonly rateLimited: string;
}

const EN: NotificationWords = {
  bell: (n) => (n === 0 ? "Notifications" : `Notifications, ${n} unread`),
  arrived: (n) => (n === 1 ? "1 unread notification" : `${n} unread notifications`),
  title: "Notifications",
  empty: "Nothing yet. You are told here when a clinic answers a request, books or moves an appointment, or a prescription is ready.",
  unread: "Unread: ",
  markAll: "Mark all as read",
  allRead: "All notifications marked as read.",
  settings: "Notification settings",
  switches: {
    title: "Notifications",
    help: "Choose what you are told about. Email is only for answers to your booking requests.",
    inApp: "In the app",
    email: "Email",
    saved: "Notification settings saved.",
    kinds: {
      "booking.accepted": "Booking request accepted",
      "booking.declined": "Booking request declined",
      "booking.proposed": "Clinic suggests another time",
      "booking.expired": "Booking request not answered in time",
      "appointment.confirmed": "Appointment booked",
      "appointment.moved": "Appointment moved",
      "appointment.cancelled": "Appointment cancelled",
      "prescription.ready": "Prescription ready",
      "medicine.due": "Medicine time",
    },
  },
  liveButton: "Live queue",
  liveOpening: "Opening the live queue…",
};

const HI: NotificationWords = {
  bell: (n) => (n === 0 ? "सूचनाएँ" : `सूचनाएँ, ${n} बिना पढ़ी`),
  arrived: (n) => (n === 1 ? "1 बिना पढ़ी सूचना" : `${n} बिना पढ़ी सूचनाएँ`),
  title: "सूचनाएँ",
  empty: "अभी कुछ नहीं। क्लिनिक आपके अनुरोध का जवाब दे, अपॉइंटमेंट बुक करे या बदले, या पर्चा तैयार हो, तो यहाँ बताया जाएगा।",
  unread: "बिना पढ़ी: ",
  markAll: "सब पढ़ी हुई करें",
  allRead: "सभी सूचनाएँ पढ़ी हुई कर दी गईं।",
  settings: "सूचना सेटिंग",
  switches: {
    title: "सूचनाएँ",
    help: "चुनें कि आपको किस बारे में बताया जाए। ईमेल सिर्फ़ बुकिंग अनुरोधों के जवाब के लिए है।",
    inApp: "ऐप में",
    email: "ईमेल",
    saved: "सूचना सेटिंग सहेज दी गई।",
    kinds: {
      "booking.accepted": "बुकिंग अनुरोध मंज़ूर",
      "booking.declined": "बुकिंग अनुरोध नामंज़ूर",
      "booking.proposed": "क्लिनिक ने दूसरा समय सुझाया",
      "booking.expired": "बुकिंग अनुरोध का समय पर जवाब नहीं",
      "appointment.confirmed": "अपॉइंटमेंट बुक हुआ",
      "appointment.moved": "अपॉइंटमेंट बदला गया",
      "appointment.cancelled": "अपॉइंटमेंट रद्द",
      "prescription.ready": "पर्चा तैयार",
      "medicine.due": "दवा का समय",
    },
  },
  liveButton: "लाइव कतार",
  liveOpening: "लाइव कतार खुल रही है…",
};

const LIVE_EN: LiveWords = {
  lang: "en",
  switchTo: "हिन्दी",
  switchLabel: "हिन्दी में देखें",
  heading: "Live queue",
  yourToken: (n) => `Your token: ${n}`,
  yourSlot: (time) => `Your time: ${time}`,
  ahead: (n) => (n === 0 ? "Nobody is ahead of you." : n === 1 ? "1 person ahead of you" : `${n} people ahead of you`),
  nowSeeing: (what) => `Now seeing: ${what}`,
  token: (n) => `token ${n}`,
  nobodyYet: "Now seeing: nobody yet",
  states: {
    NOT_STARTED: "The session has not started yet.",
    WAITING: "Please wait; you will be called.",
    YOUR_TURN: "It is your turn. Please go in.",
    DONE: "Your visit is over. Get well soon.",
    CANCELLED: "This appointment was cancelled. Please call the clinic.",
  },
  startsAt: (time) => `The session starts at ${time}.`,
  updated: (time) => `Updated ${time}`,
  refreshNote: "This page updates by itself every 20 seconds.",
  offline: "Could not update. Showing the last known place; trying again.",
  invalid: "This link is not valid. Please ask the clinic for a new one.",
  expired: "This link has expired. It works only on the day of the appointment.",
  unavailable: "The live queue is not available right now. Please try again shortly.",
  rateLimited: "Too many refreshes. Please wait a minute.",
};

const LIVE_HI: LiveWords = {
  lang: "hi",
  switchTo: "English",
  switchLabel: "View in English",
  heading: "लाइव कतार",
  yourToken: (n) => `आपका टोकन: ${n}`,
  yourSlot: (time) => `आपका समय: ${time}`,
  ahead: (n) => (n === 0 ? "आपसे आगे कोई नहीं है।" : n === 1 ? "आपसे आगे 1 व्यक्ति" : `आपसे आगे ${n} लोग`),
  nowSeeing: (what) => `अभी देख रहे हैं: ${what}`,
  token: (n) => `टोकन ${n}`,
  nobodyYet: "अभी देख रहे हैं: अभी कोई नहीं",
  states: {
    NOT_STARTED: "सत्र अभी शुरू नहीं हुआ है।",
    WAITING: "कृपया प्रतीक्षा करें; आपको बुलाया जाएगा।",
    YOUR_TURN: "आपकी बारी है। कृपया अंदर जाएँ।",
    DONE: "आपकी मुलाक़ात पूरी हुई। जल्दी ठीक हो जाएँ।",
    CANCELLED: "यह अपॉइंटमेंट रद्द हो गया। कृपया क्लिनिक को फ़ोन करें।",
  },
  startsAt: (time) => `सत्र ${time} बजे शुरू होगा।`,
  updated: (time) => `${time} पर अपडेट हुआ`,
  refreshNote: "यह पेज हर 20 सेकंड में अपने-आप अपडेट होता है।",
  offline: "अपडेट नहीं हो सका। आख़िरी जानकारी दिख रही है; फिर कोशिश हो रही है।",
  invalid: "यह लिंक सही नहीं है। कृपया क्लिनिक से नया लिंक माँगें।",
  expired: "इस लिंक की अवधि ख़त्म हो गई। यह सिर्फ़ अपॉइंटमेंट वाले दिन चलता है।",
  unavailable: "लाइव कतार अभी उपलब्ध नहीं है। कृपया थोड़ी देर में फिर कोशिश करें।",
  rateLimited: "बहुत बार रीफ़्रेश हुआ। कृपया एक मिनट रुकें।",
};

export function notificationWords(language: PortalLanguage): NotificationWords {
  return language === "hi" ? HI : EN;
}

export function liveWords(language: PortalLanguage): LiveWords {
  return language === "hi" ? LIVE_HI : LIVE_EN;
}
