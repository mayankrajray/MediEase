/**
 * Every word of the patient portal, in English and Hindi (M6b-P2; spec R21, NFR-11, FR-PRT-04).
 *
 * Plain typed objects, no i18n library, so the portal stays inside the patient-page budget (R23).
 * The doctor's own text and the prescription page's labels come from the API in the chosen
 * language; nothing clinical is ever written here. Hindi to be reviewed with the phrasebook (L-07),
 * as the prescription page's.
 */

export type PortalLanguage = "en" | "hi";

/** The signed-out pages' language (decision 2A); also seeds a new account's. Not a secret. */
export const PORTAL_LANGUAGE_COOKIE = "me_pt_lang";

export function parsePortalLanguage(value: string | null | undefined): PortalLanguage {
  return value === "hi" ? "hi" : "en";
}

/** A patient-facing status for an appointment (spec R18); text, never colour alone. */
export type AppointmentWord = "confirmed" | "atClinic" | "completed" | "cancelled" | "missed";

export function appointmentWord(status: string): AppointmentWord {
  switch (status) {
    case "BOOKED":
      return "confirmed";
    case "ARRIVED":
    case "IN_CONSULTATION":
      return "atClinic";
    case "COMPLETED":
      return "completed";
    case "CANCELLED":
      return "cancelled";
    default:
      return "missed";
  }
}

export interface PortalStrings {
  readonly lang: PortalLanguage;
  readonly locale: string;
  readonly brandTagline: string;
  readonly switchLanguage: string;
  readonly switchLanguageLabel: string;
  readonly nav: { readonly label: string; readonly home: string; readonly appointments: string; readonly prescriptions: string; readonly account: string };
  readonly loading: string;
  readonly tryAgain: string;
  readonly goHome: string;
  readonly notFound: string;
  readonly home: {
    readonly hello: (name: string) => string;
    readonly noAppointments: string;
    readonly freshHelp: string;
    readonly findDoctor: string;
    readonly haveInvitation: string;
    readonly howToLink: string;
    readonly nextAppointment: string;
    readonly noUpcoming: string;
    readonly latestPrescription: string;
    readonly upcomingReminders: string;
    readonly seeAll: string;
  };
  readonly find: { readonly title: string; readonly soon: string; readonly meanwhile: string; readonly clinicPage: string; readonly invitation: string; readonly prescription: string };
  readonly appointments: {
    readonly title: string;
    readonly empty: string;
    readonly upcoming: string;
    readonly past: string;
    readonly none: string;
    readonly call: string;
    readonly token: (n: number) => string;
    readonly session: (from: string, to: string) => string;
    readonly words: Readonly<Record<AppointmentWord, string>>;
    readonly reminders: string;
  };
  readonly reminders: {
    readonly followUp: string;
    readonly appointment: string;
    readonly due: (when: string) => string;
    readonly status: (status: string) => string;
  };
  readonly prescriptions: {
    readonly title: string;
    readonly empty: string;
    readonly issued: (day: string) => string;
    readonly updated: string;
    readonly open: string;
    readonly download: string;
    readonly downloading: string;
    readonly back: string;
  };
  readonly account: {
    readonly title: string;
    readonly signsInWith: string;
    readonly google: string;
    readonly password: string;
    readonly email: string;
    readonly verified: string;
    readonly notVerified: string;
    readonly confirmEmail: string;
    readonly confirmEmailHelp: string;
    readonly resend: string;
    readonly sending: string;
    readonly sent: string;
    readonly language: string;
    readonly clinics: string;
    readonly noClinics: string;
    readonly linkedHow: (how: string, since: string) => string;
    readonly byInvite: string;
    readonly byPrescription: string;
    readonly unlink: string;
    readonly unlinkConfirm: (clinic: string) => string;
    readonly unlinkYes: string;
    readonly cancel: string;
    readonly unlinked: (clinic: string) => string;
    readonly signOut: string;
    readonly signingOut: string;
  };
  readonly link: {
    readonly heading: (clinic: string) => string;
    readonly help: (clinic: string) => string;
    readonly link: string;
    readonly linking: string;
    readonly notMe: string;
    readonly invalidTitle: string;
    readonly invalid: string;
    readonly couldNotOpen: string;
    readonly done: string;
    readonly doneHelp: (clinic: string, who: string) => string;
    readonly goAccount: string;
    readonly rxHeading: string;
    readonly rxHelp: string;
    readonly last4: string;
    readonly save: string;
    readonly saving: string;
    readonly verifyFirst: string;
    readonly verifyFirstHelp: string;
  };
  readonly errors: Readonly<Record<string, string>>;
  readonly triesLeft: (n: string) => string;
  readonly signIn: {
    readonly heading: string;
    readonly email: string;
    readonly password: string;
    readonly submit: string;
    readonly submitting: string;
    readonly forgot: string;
    readonly newHere: string;
    readonly create: string;
  };
  readonly signUp: {
    readonly heading: string;
    readonly intro: string;
    readonly name: string;
    readonly submit: string;
    readonly submitting: string;
    readonly passwordHelp: string;
    readonly passwordTooShort: string;
    readonly haveAccount: string;
    readonly signIn: string;
  };
}

const EN: PortalStrings = {
  lang: "en",
  locale: "en-IN",
  brandTagline: "Your appointments and prescriptions, in one place",
  switchLanguage: "हिन्दी",
  switchLanguageLabel: "हिन्दी में देखें (view in Hindi)",
  nav: { label: "Patient app", home: "Home", appointments: "Appointments", prescriptions: "Prescriptions", account: "Account" },
  loading: "Loading…",
  tryAgain: "Try again",
  goHome: "Go to Home",
  notFound: "We couldn't find this. It may belong to a clinic that is no longer linked to your account.",
  home: {
    hello: (name) => `Hello, ${name}`,
    noAppointments: "No appointments yet",
    freshHelp: "Find a doctor to book a visit, or link the records your clinic already keeps for you.",
    findDoctor: "Find a doctor",
    haveInvitation: "Have an invitation from your clinic?",
    howToLink:
      "Open the invitation link or scan the code your clinic gave you, or choose “Save to my MediEase” on a prescription link from your clinic. Your appointments and prescriptions from that clinic then appear here.",
    nextAppointment: "Next appointment",
    noUpcoming: "No upcoming appointments.",
    latestPrescription: "Latest prescription",
    upcomingReminders: "Coming up",
    seeAll: "See all",
  },
  find: {
    title: "Find a doctor",
    soon: "Searching for doctors and clinics on MediEase is coming soon.",
    meanwhile: "Until then you can:",
    clinicPage: "open your clinic's own MediEase page, if it gave you one;",
    invitation: "ask your clinic for an invitation to the patient app;",
    prescription: "choose “Save to my MediEase” on a prescription link from your clinic.",
  },
  appointments: {
    title: "My appointments",
    empty: "No appointments yet. Link your clinic's records to see them here.",
    upcoming: "Upcoming",
    past: "Past",
    none: "None",
    call: "Call the clinic",
    token: (n) => `Token ${n}`,
    session: (from, to) => `session ${from}–${to}`,
    words: { confirmed: "Confirmed", atClinic: "At the clinic", completed: "Completed", cancelled: "Cancelled", missed: "Missed" },
    reminders: "Reminders",
  },
  reminders: {
    followUp: "Follow-up visit",
    appointment: "Appointment reminder",
    due: (when) => `Due ${when}`,
    status: (status) =>
      ({
        SCHEDULED: "Scheduled",
        SENT: "Sent",
        DELIVERED: "Delivered",
        READ: "Read",
        FAILED: "Not delivered",
        CANCELLED: "Cancelled",
        SKIPPED_NO_CONSENT: "Not sent (no consent)",
      })[status] ?? status,
  },
  prescriptions: {
    title: "My prescriptions",
    empty: "No prescriptions yet.",
    issued: (day) => `Issued ${day}`,
    updated: "Updated by the doctor",
    open: "Open",
    download: "Download PDF",
    downloading: "Downloading…",
    back: "All prescriptions",
  },
  account: {
    title: "Account",
    signsInWith: "Signs in with",
    google: "Google",
    password: "Email and password",
    email: "Email",
    verified: "Verified",
    notVerified: "Not verified yet",
    confirmEmail: "Confirm your email",
    confirmEmailHelp: "We sent you a link. Open it to confirm this is your address.",
    resend: "Resend the email",
    sending: "Sending…",
    sent: "A new link is on its way. It works once and lasts 24 hours.",
    language: "Language",
    clinics: "Your clinics",
    noClinics: "No clinic linked yet.",
    linkedHow: (how, since) => `Linked ${how} since ${since}`,
    byInvite: "by invitation",
    byPrescription: "from a prescription link",
    unlink: "Unlink",
    unlinkConfirm: (clinic) =>
      `Unlink ${clinic}? Its appointments, prescriptions and reminders will disappear from your account. The clinic keeps its own records.`,
    unlinkYes: "Yes, unlink",
    cancel: "Cancel",
    unlinked: (clinic) => `${clinic} is no longer linked.`,
    signOut: "Sign out",
    signingOut: "Signing out…",
  },
  link: {
    heading: (clinic) => `Link your records at ${clinic}`,
    help: (clinic) =>
      `Your appointments, prescriptions and reminders from ${clinic} will appear in this account. Only link records that are yours.`,
    link: "Link",
    linking: "Linking…",
    notMe: "Not me",
    invalidTitle: "This invitation is no longer valid",
    invalid: "It may have been used already, replaced by a newer one, or expired. Ask the clinic for a new one.",
    couldNotOpen: "Could not open this invitation",
    done: "Linked",
    doneHelp: (clinic, who) => `Your records at ${clinic} (${who}) are now in your MediEase account.`,
    goAccount: "Go to Home",
    rxHeading: "Save your records to MediEase",
    rxHelp:
      "Enter the last 4 digits of the phone number the clinic has for you. Your appointments, prescriptions and reminders from that clinic will then appear in this account.",
    last4: "Last 4 digits of your phone number",
    save: "Save to my MediEase",
    saving: "Saving…",
    verifyFirst: "Confirm your email first",
    verifyFirstHelp:
      "To save a prescription to your account, confirm your email address with the link we sent you, then open this page again. Or ask the clinic for an invitation to the patient app.",
  },
  errors: {
    PRT_INVITE_INVALID: "This invitation is no longer valid. Ask the clinic for a new one.",
    PRT_ALREADY_LINKED: "These records can't be linked to this account. Contact the clinic.",
    PRT_UNVERIFIED_ACCOUNT: "Confirm your email address first, then try again.",
    LINK_CHALLENGE_FAILED: "Those digits don't match.",
    LINK_LOCKED: "Too many attempts. Please contact the clinic.",
    LINK_INVALID: "This link isn't valid.",
    LINK_EXPIRED: "This link has expired. Ask the clinic for a new one.",
    LINK_REVOKED: "This link is no longer active. Ask the clinic for a new one.",
    LINK_RATE_LIMITED: "Too many requests. Please wait a minute and try again.",
    WEB_API_UNREACHABLE: "We couldn't reach MediEase. Check your connection and try again.",
  },
  triesLeft: (n) => `Those digits don't match. ${n} ${n === "1" ? "try" : "tries"} left.`,
  signIn: {
    heading: "Sign in to your health account",
    email: "Email",
    password: "Password",
    submit: "Sign in",
    submitting: "Signing in…",
    forgot: "Forgot password?",
    newHere: "New to MediEase?",
    create: "Create an account",
  },
  signUp: {
    heading: "Create your health account",
    intro: "One account for your appointments and prescriptions at every clinic that uses MediEase.",
    name: "Your name",
    submit: "Create account",
    submitting: "Creating…",
    passwordHelp: "At least 12 characters.",
    passwordTooShort: "Use at least 12 characters.",
    haveAccount: "Already have an account?",
    signIn: "Sign in",
  },
};

const HI: PortalStrings = {
  lang: "hi",
  locale: "hi-IN",
  brandTagline: "आपके अपॉइंटमेंट और पर्चे, एक जगह",
  switchLanguage: "English",
  switchLanguageLabel: "View in English (अंग्रेज़ी में देखें)",
  nav: { label: "मरीज़ ऐप", home: "होम", appointments: "अपॉइंटमेंट", prescriptions: "पर्चे", account: "खाता" },
  loading: "लोड हो रहा है…",
  tryAgain: "फिर कोशिश करें",
  goHome: "होम पर जाएँ",
  notFound: "यह नहीं मिला। हो सकता है यह किसी ऐसे क्लिनिक का हो जो अब आपके खाते से जुड़ा नहीं है।",
  home: {
    hello: (name) => `नमस्ते, ${name}`,
    noAppointments: "अभी कोई अपॉइंटमेंट नहीं",
    freshHelp: "डॉक्टर ढूँढकर अपॉइंटमेंट लें, या आपके क्लिनिक के पास जो रिकॉर्ड हैं उन्हें जोड़ें।",
    findDoctor: "डॉक्टर ढूँढें",
    haveInvitation: "क्या आपके क्लिनिक ने आमंत्रण दिया है?",
    howToLink:
      "क्लिनिक का दिया आमंत्रण लिंक खोलें या कोड स्कैन करें, या क्लिनिक के पर्चे के लिंक पर “मेरे MediEase में सहेजें” चुनें। फिर उस क्लिनिक के अपॉइंटमेंट और पर्चे यहाँ दिखेंगे।",
    nextAppointment: "अगला अपॉइंटमेंट",
    noUpcoming: "कोई आने वाला अपॉइंटमेंट नहीं।",
    latestPrescription: "नया पर्चा",
    upcomingReminders: "आगे",
    seeAll: "सब देखें",
  },
  find: {
    title: "डॉक्टर ढूँढें",
    soon: "MediEase पर डॉक्टर और क्लिनिक खोजने की सुविधा जल्द आ रही है।",
    meanwhile: "तब तक आप:",
    clinicPage: "अपने क्लिनिक का MediEase पेज खोल सकते हैं, अगर उन्होंने दिया हो;",
    invitation: "अपने क्लिनिक से मरीज़ ऐप का आमंत्रण माँग सकते हैं;",
    prescription: "क्लिनिक के पर्चे के लिंक पर “मेरे MediEase में सहेजें” चुन सकते हैं।",
  },
  appointments: {
    title: "मेरे अपॉइंटमेंट",
    empty: "अभी कोई अपॉइंटमेंट नहीं। उन्हें यहाँ देखने के लिए अपने क्लिनिक के रिकॉर्ड जोड़ें।",
    upcoming: "आने वाले",
    past: "पिछले",
    none: "कोई नहीं",
    call: "क्लिनिक को फ़ोन करें",
    token: (n) => `टोकन ${n}`,
    session: (from, to) => `सत्र ${from}–${to}`,
    words: { confirmed: "पक्का", atClinic: "क्लिनिक में", completed: "पूरा हुआ", cancelled: "रद्द", missed: "नहीं आए" },
    reminders: "रिमाइंडर",
  },
  reminders: {
    followUp: "दोबारा दिखाने की तारीख़",
    appointment: "अपॉइंटमेंट रिमाइंडर",
    due: (when) => `${when} को`,
    status: (status) =>
      ({
        SCHEDULED: "तय",
        SENT: "भेजा गया",
        DELIVERED: "पहुँच गया",
        READ: "पढ़ा गया",
        FAILED: "नहीं पहुँचा",
        CANCELLED: "रद्द",
        SKIPPED_NO_CONSENT: "नहीं भेजा (अनुमति नहीं)",
      })[status] ?? status,
  },
  prescriptions: {
    title: "मेरे पर्चे",
    empty: "अभी कोई पर्चा नहीं।",
    issued: (day) => `${day} को दिया गया`,
    updated: "डॉक्टर ने बदला",
    open: "खोलें",
    download: "PDF डाउनलोड करें",
    downloading: "डाउनलोड हो रहा है…",
    back: "सभी पर्चे",
  },
  account: {
    title: "खाता",
    signsInWith: "साइन इन",
    google: "Google",
    password: "ईमेल और पासवर्ड",
    email: "ईमेल",
    verified: "पुष्टि हो गई",
    notVerified: "अभी पुष्टि नहीं हुई",
    confirmEmail: "अपने ईमेल की पुष्टि करें",
    confirmEmailHelp: "हमने आपको एक लिंक भेजा है। इसे खोलकर पुष्टि करें कि यह आपका पता है।",
    resend: "ईमेल फिर भेजें",
    sending: "भेज रहे हैं…",
    sent: "नया लिंक भेज दिया गया है। यह एक बार और 24 घंटे तक काम करेगा।",
    language: "भाषा",
    clinics: "आपके क्लिनिक",
    noClinics: "अभी कोई क्लिनिक नहीं जुड़ा।",
    linkedHow: (how, since) => `${since} से ${how} जुड़ा`,
    byInvite: "आमंत्रण से",
    byPrescription: "पर्चे के लिंक से",
    unlink: "हटाएँ",
    unlinkConfirm: (clinic) =>
      `${clinic} को हटाएँ? इसके अपॉइंटमेंट, पर्चे और रिमाइंडर आपके खाते से हट जाएँगे। क्लिनिक के अपने रिकॉर्ड बने रहेंगे।`,
    unlinkYes: "हाँ, हटाएँ",
    cancel: "रहने दें",
    unlinked: (clinic) => `${clinic} अब जुड़ा नहीं है।`,
    signOut: "साइन आउट",
    signingOut: "साइन आउट हो रहा है…",
  },
  link: {
    heading: (clinic) => `${clinic} के अपने रिकॉर्ड जोड़ें`,
    help: (clinic) =>
      `${clinic} के आपके अपॉइंटमेंट, पर्चे और रिमाइंडर इस खाते में दिखेंगे। सिर्फ़ अपने रिकॉर्ड जोड़ें।`,
    link: "जोड़ें",
    linking: "जोड़ रहे हैं…",
    notMe: "यह मैं नहीं हूँ",
    invalidTitle: "यह आमंत्रण अब मान्य नहीं है",
    invalid: "हो सकता है इसका इस्तेमाल हो चुका हो, नया आमंत्रण भेजा गया हो, या समय-सीमा ख़त्म हो गई हो। क्लिनिक से नया माँगें।",
    couldNotOpen: "यह आमंत्रण नहीं खुल सका",
    done: "जुड़ गया",
    doneHelp: (clinic, who) => `${clinic} के आपके रिकॉर्ड (${who}) अब आपके MediEase खाते में हैं।`,
    goAccount: "होम पर जाएँ",
    rxHeading: "अपने रिकॉर्ड MediEase में सहेजें",
    rxHelp:
      "क्लिनिक के पास जो फ़ोन नंबर है, उसके आख़िरी 4 अंक लिखें। फिर उस क्लिनिक के आपके अपॉइंटमेंट, पर्चे और रिमाइंडर इस खाते में दिखेंगे।",
    last4: "आपके फ़ोन नंबर के आख़िरी 4 अंक",
    save: "मेरे MediEase में सहेजें",
    saving: "सहेज रहे हैं…",
    verifyFirst: "पहले अपने ईमेल की पुष्टि करें",
    verifyFirstHelp:
      "पर्चा अपने खाते में सहेजने के लिए, हमारे भेजे लिंक से अपने ईमेल की पुष्टि करें और फिर यह पेज दोबारा खोलें। या क्लिनिक से मरीज़ ऐप का आमंत्रण माँगें।",
  },
  errors: {
    PRT_INVITE_INVALID: "यह आमंत्रण अब मान्य नहीं है। क्लिनिक से नया माँगें।",
    PRT_ALREADY_LINKED: "ये रिकॉर्ड इस खाते से नहीं जुड़ सकते। क्लिनिक से संपर्क करें।",
    PRT_UNVERIFIED_ACCOUNT: "पहले अपने ईमेल की पुष्टि करें, फिर कोशिश करें।",
    LINK_CHALLENGE_FAILED: "ये अंक मेल नहीं खाते।",
    LINK_LOCKED: "बहुत ज़्यादा कोशिशें हुईं। क्लिनिक से संपर्क करें।",
    LINK_INVALID: "यह लिंक सही नहीं है।",
    LINK_EXPIRED: "इस लिंक की समय-सीमा ख़त्म हो गई है। क्लिनिक से नया लिंक माँगें।",
    LINK_REVOKED: "यह लिंक अब काम नहीं करता। क्लिनिक से नया लिंक माँगें।",
    LINK_RATE_LIMITED: "बहुत ज़्यादा अनुरोध। एक मिनट रुककर फिर कोशिश करें।",
    WEB_API_UNREACHABLE: "MediEase से संपर्क नहीं हो सका। अपना इंटरनेट जाँचें और फिर कोशिश करें।",
  },
  triesLeft: (n) => `ये अंक मेल नहीं खाते। ${n} बार और कोशिश कर सकते हैं।`,
  signIn: {
    heading: "अपने हेल्थ खाते में साइन इन करें",
    email: "ईमेल",
    password: "पासवर्ड",
    submit: "साइन इन",
    submitting: "साइन इन हो रहा है…",
    forgot: "पासवर्ड भूल गए?",
    newHere: "MediEase पर नए हैं?",
    create: "खाता बनाएँ",
  },
  signUp: {
    heading: "अपना हेल्थ खाता बनाएँ",
    intro: "MediEase इस्तेमाल करने वाले हर क्लिनिक के आपके अपॉइंटमेंट और पर्चों के लिए एक खाता।",
    name: "आपका नाम",
    submit: "खाता बनाएँ",
    submitting: "बना रहे हैं…",
    passwordHelp: "कम से कम 12 अक्षर।",
    passwordTooShort: "कम से कम 12 अक्षर लिखें।",
    haveAccount: "पहले से खाता है?",
    signIn: "साइन इन",
  },
};

export function portalStrings(language: PortalLanguage): PortalStrings {
  return language === "hi" ? HI : EN;
}

function zoned(iso: string, timeZone: string, locale: string, options: Intl.DateTimeFormatOptions): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "–";
  try {
    return new Intl.DateTimeFormat(locale, { ...options, timeZone }).format(date);
  } catch {
    return new Intl.DateTimeFormat(locale, { ...options, timeZone: "UTC" }).format(date);
  }
}

/** "Mon, 19 Oct" on the clinic's calendar (spec R22). */
export function portalDay(iso: string, timeZone: string, s: PortalStrings): string {
  return zoned(iso, timeZone, s.locale, { weekday: "short", day: "numeric", month: "short" });
}

/** "10:30 am" on the clinic's clock. */
export function portalTime(iso: string, timeZone: string, s: PortalStrings): string {
  return zoned(iso, timeZone, s.locale, { hour: "numeric", minute: "2-digit" });
}

/** "19 Oct 2026" for an instant, on the clinic's calendar. */
export function portalDate(iso: string, timeZone: string, s: PortalStrings): string {
  return zoned(iso, timeZone, s.locale, { day: "numeric", month: "short", year: "numeric" });
}

/** "19 Oct 2026" for a calendar date (`YYYY-MM-DD`, no zone). */
export function portalCalendarDate(isoDate: string, s: PortalStrings): string {
  return zoned(`${isoDate}T12:00:00Z`, "UTC", s.locale, { day: "numeric", month: "short", year: "numeric" });
}
