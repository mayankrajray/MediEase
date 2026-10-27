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
  readonly nav: {
    readonly label: string;
    readonly home: string;
    readonly appointments: string;
    readonly medicines: string;
    readonly prescriptions: string;
    readonly account: string;
  };
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
  readonly find: {
    readonly title: string;
    readonly soon: string;
    readonly search: string;
    readonly meanwhile: string;
    readonly clinicPage: string;
    readonly invitation: string;
    readonly prescription: string;
  };
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
  /** M6d-P4 (billing R52): the linked records' bills and their receipts. */
  readonly bills: {
    readonly title: string;
    readonly due: (amount: string) => string;
    readonly settled: string;
    readonly cancelled: string;
    readonly download: string;
  };
  /** M6d-P6 (visit-attachments R11, R12): reports the doctor shared. */
  readonly reports: {
    readonly title: string;
    readonly visitOn: (date: string) => string;
    readonly open: string;
  };
  /** M7a (spec assistant §6): the assistant page. */
  readonly assistant: {
    readonly title: string;
    readonly intro: string;
    readonly open: string;
    readonly openHelp: string;
    readonly choose: string;
    readonly noChoice: string;
    readonly noPrescriptions: string;
    readonly option: (doctor: string, clinic: string, day: string) => string;
    readonly message: string;
    readonly placeholder: string;
    readonly send: string;
    readonly sending: string;
    readonly you: string;
    readonly bot: string;
    readonly confirm: string;
    readonly confirming: string;
    readonly cancel: string;
    readonly cancelled: string;
    readonly conversation: string;
    readonly empty: string;
    /** M7b (spec prescription-uploads §8): a prescription not in the account, by file or code. */
    readonly upload: {
      readonly title: string;
      readonly intro: string;
      readonly privacy: string;
      readonly file: string;
      readonly fileHelp: string;
      readonly send: string;
      readonly sending: string;
      readonly or: string;
      readonly code: string;
      readonly codeHelp: string;
      readonly verify: string;
      readonly checking: string;
      readonly slow: string;
      readonly challengeTitle: string;
      readonly challengeHelp: string;
      readonly last4: string;
      readonly check: string;
      readonly attemptsLeft: (n: number) => string;
      readonly verified: (doctor: string, clinic: string, day: string, version: number) => string;
      readonly representative: (until: string) => string;
      readonly historical: (version: number, latest: number, latestDay: string) => string;
      readonly chooseVersion: string;
      readonly useUploaded: (version: number) => string;
      readonly useLatest: (version: number) => string;
      readonly using: (version: number) => string;
      readonly asking: string;
      readonly remove: string;
      readonly tryAgain: string;
      readonly rejected: Readonly<Record<string, string>>;
      readonly rejectedOther: string;
    };
  };
  /** M6b-P3 (spec R36-R44): the planner's own words; the medicine's come from the API. */
  readonly medicines: {
    readonly title: string;
    readonly views: string;
    readonly today: string;
    readonly courses: string;
    readonly safety: string;
    readonly contact: string;
    readonly asWritten: string;
    readonly empty: string;
    readonly nothingOn: string;
    readonly previousDay: string;
    readonly nextDay: string;
    readonly backToToday: string;
    readonly dayOf: (n: number, m: number) => string;
    readonly from: (date: string) => string;
    readonly until: (date: string) => string;
    readonly by: (doctor: string, clinic: string) => string;
    readonly remindMe: (slot: string, time: string) => string;
    readonly reminderTime: (slot: string) => string;
    readonly reminderOn: (time: string) => string;
    readonly reminderSaved: string;
    readonly saveTime: string;
    /** M6b-P3b (R45-R48): the patient's own marks. */
    readonly doses: {
      readonly taken: string;
      readonly skipped: string;
      readonly notRecorded: string;
      readonly upcoming: string;
      readonly takenAt: (time: string) => string;
      readonly skippedAt: (time: string) => string;
      readonly markAs: (state: string, medicine: string, slot: string) => string;
      readonly change: string;
      readonly clear: string;
      readonly unsure: string;
      readonly history: string;
      readonly hideHistory: string;
      readonly historyHeading: (version: number) => string;
      readonly counts: (taken: number, skipped: number, notRecorded: number) => string;
      readonly saved: string;
      readonly private: string;
    };
    readonly remindersLater: string;
    readonly updated: string;
    readonly noCourses: string;
  };
  readonly account: {
    readonly title: string;
    readonly times: string;
    readonly timesHelp: string;
    readonly slots: { readonly morning: string; readonly afternoon: string; readonly evening: string; readonly night: string };
    readonly saveTimes: string;
    readonly timesSaved: string;
    readonly timesOrder: string;
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
  nav: { label: "Patient app", home: "Home", appointments: "Appointments", medicines: "Medicines", prescriptions: "Prescriptions", account: "Account" },
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
    soon: "Search the doctors and clinics on MediEase. MediEase has checked every doctor's registration.",
    search: "Search doctors and clinics",
    meanwhile: "You can also:",
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
  bills: {
    title: "Bills",
    due: (amount) => `${amount} due`,
    settled: "Paid",
    cancelled: "Cancelled",
    download: "Receipt (PDF)",
  },
  reports: {
    title: "Reports from your doctor",
    visitOn: (date) => `Visit on ${date}`,
    open: "Open",
  },
  assistant: {
    title: "Assistant",
    intro:
      "Ask about your appointments, booking a visit, or a prescription. The assistant repeats what your doctor wrote; it cannot give medical advice.",
    open: "Ask the assistant",
    openHelp: "Questions about a prescription, your appointments or booking.",
    choose: "Prescription to ask about",
    noChoice: "None",
    noPrescriptions: "No prescriptions in your account yet.",
    option: (doctor, clinic, day) => `${doctor}, ${clinic} (${day})`,
    message: "Your message",
    placeholder: "For example: when do I take my medicine?",
    send: "Send",
    sending: "Sending…",
    you: "You",
    bot: "Assistant",
    confirm: "Confirm",
    confirming: "Confirming…",
    cancel: "Cancel",
    cancelled: "Nothing was changed.",
    conversation: "Conversation",
    empty: "Ask a question to start.",
    upload: {
      title: "A prescription not in your account",
      intro:
        "For a family member's prescription, or one you were given on paper: upload a photo or the PDF, or type the verification code printed at the bottom.",
      privacy:
        "Only the MediEase code on it is read. The file is deleted once it is checked, and clinic staff never see it. The assistant explains the clinic's own record, not the file.",
      file: "Photo or PDF of the prescription",
      fileHelp: "PDF, JPEG or PNG, up to 10 MB. Make sure the square code at the bottom is in the picture.",
      send: "Upload",
      sending: "Uploading…",
      or: "Or",
      code: "Verification code",
      codeHelp: "The code printed under “Verification code”, for example 0192f3a4-7c1e-7b2a-9d40-5e6f7a8b9c0d.",
      verify: "Check code",
      checking: "Checking your file…",
      slow: "This is taking longer than usual. You can wait, or type the code instead.",
      challengeTitle: "Confirm the patient",
      challengeHelp:
        "This prescription is not in your account. Enter the last 4 digits of the patient's phone number, as the clinic has it.",
      last4: "Last 4 digits of the patient's phone",
      check: "Confirm",
      attemptsLeft: (n) => (n === 1 ? "That did not match. 1 attempt left." : `That did not match. ${n} attempts left.`),
      verified: (doctor, clinic, day, version) => `Verified: ${doctor}, ${clinic}, ${day} (version ${version}).`,
      representative: (until) =>
        `You can ask about this prescription until ${until}. It has not been added to your account.`,
      historical: (version, latest, latestDay) =>
        `This is an older version (version ${version}). The doctor issued version ${latest} on ${latestDay}. Which one should the assistant explain?`,
      chooseVersion: "Version to explain",
      useUploaded: (version) => `The one I uploaded (version ${version}, older)`,
      useLatest: (version) => `The latest (version ${version})`,
      using: (version) => `The assistant will explain version ${version}.`,
      asking: "Asking about the verified prescription.",
      remove: "Remove",
      tryAgain: "Try another photo or type the code.",
      rejected: {
        UPL_INFECTED: "The file was refused by the safety check and deleted.",
        UPL_SCAN_UNAVAILABLE: "The file could not be checked right now and was deleted. Please try again later.",
        UPL_NO_IDENTIFIER: "No MediEase code was found on it. Take a clearer photo of the square code, or type the code.",
        UPL_AMBIGUOUS: "It shows more than one prescription. Upload one prescription at a time.",
        UPL_UNREADABLE: "The file could not be read.",
        UPL_LOCKED: "Too many wrong attempts. This upload has been stopped.",
        UPL_ABANDONED: "The check did not finish and the file was deleted.",
        UPL_EXPIRED: "This check has expired.",
        UPL_WITHDRAWN: "Removed.",
        UPL_FILE_MISSING: "The file could not be found. Please upload it again.",
      },
      rejectedOther: "This prescription could not be verified.",
    },
  },
  medicines: {
    title: "My medicines",
    views: "Show",
    today: "Today",
    courses: "Courses",
    safety: "This plan only lays out your prescription. If anything is unclear, ask your doctor.",
    contact: "Contact your clinic",
    asWritten: "As the doctor wrote",
    empty: "No medicines from your prescriptions yet.",
    nothingOn: "No medicines on this day.",
    previousDay: "Previous day",
    nextDay: "Next day",
    backToToday: "Today",
    dayOf: (n, m) => `Day ${n} of ${m}`,
    from: (date) => `From ${date}`,
    until: (date) => `Until ${date}`,
    by: (doctor, clinic) => `${doctor} · ${clinic}`,
    remindMe: (slot, time) => `Remind me · ${slot} (${time})`,
    reminderTime: (slot) => `Reminder time, ${slot}`,
    reminderOn: (time) => `Reminder on at ${time}`,
    reminderSaved: "Your reminder choice is saved.",
    saveTime: "Save time",
    doses: {
      taken: "Taken",
      skipped: "Skipped",
      notRecorded: "Not recorded",
      upcoming: "Upcoming",
      takenAt: (time) => `Taken at ${time}`,
      skippedAt: (time) => `Skipped at ${time}`,
      markAs: (state, medicine, slot) => `${state}: ${medicine}, ${slot}`,
      change: "Change",
      clear: "Clear the mark",
      unsure: "If you are unsure what to do, contact your clinic.",
      history: "History",
      hideHistory: "Hide history",
      historyHeading: (version) => `History · version ${version}`,
      counts: (taken, skipped, notRecorded) => `Taken ${taken} · Skipped ${skipped} · Not recorded ${notRecorded}`,
      saved: "Saved.",
      private: "Only you can see what you mark here. Your clinic does not.",
    },
    remindersLater: "Reminders appear under Notifications in this app at the times you choose. There is no phone alert yet, so open the app to see them.",
    updated: "This prescription was updated — set your reminders again.",
    noCourses: "No courses yet.",
  },
  account: {
    title: "Account",
    times: "Your times of day",
    timesHelp: "Used to show your medicines on a clock. They never change your prescription.",
    slots: { morning: "Morning", afternoon: "Afternoon", evening: "Evening", night: "Night" },
    saveTimes: "Save times",
    timesSaved: "Your times of day are saved.",
    timesOrder: "Each time must be later than the one before, between 05:00 and 23:30.",
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
    help: (clinic) => `Your appointments, prescriptions and reminders from ${clinic} will appear in this account. Only link records that are yours.`,
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
    PRT_DOSE_NOT_MARKABLE: "This dose can only be marked from the start of its day until 48 hours after its time.",
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
  nav: { label: "मरीज़ ऐप", home: "होम", appointments: "अपॉइंटमेंट", medicines: "दवाइयाँ", prescriptions: "पर्चे", account: "खाता" },
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
    soon: "MediEase पर डॉक्टर और क्लिनिक खोजें। MediEase ने हर डॉक्टर का पंजीकरण जाँचा है।",
    search: "डॉक्टर और क्लिनिक खोजें",
    meanwhile: "आप यह भी कर सकते हैं:",
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
  bills: {
    title: "बिल",
    due: (amount) => `${amount} बाकी`,
    settled: "भुगतान हो गया",
    cancelled: "रद्द",
    download: "रसीद (PDF)",
  },
  reports: {
    title: "डॉक्टर की भेजी रिपोर्ट",
    visitOn: (date) => `मुलाक़ात: ${date}`,
    open: "खोलें",
  },
  assistant: {
    title: "सहायक",
    intro:
      "अपनी अपॉइंटमेंट, बुकिंग या किसी पर्चे के बारे में पूछें। सहायक वही दोहराता है जो आपके डॉक्टर ने लिखा है; यह चिकित्सा सलाह नहीं दे सकता।",
    open: "सहायक से पूछें",
    openHelp: "पर्चे, अपॉइंटमेंट या बुकिंग के बारे में सवाल।",
    choose: "किस पर्चे के बारे में पूछना है",
    noChoice: "कोई नहीं",
    noPrescriptions: "आपके खाते में अभी कोई पर्चा नहीं है।",
    option: (doctor, clinic, day) => `${doctor}, ${clinic} (${day})`,
    message: "आपका संदेश",
    placeholder: "उदाहरण: मुझे दवा कब लेनी है?",
    send: "भेजें",
    sending: "भेजा जा रहा है…",
    you: "आप",
    bot: "सहायक",
    confirm: "पुष्टि करें",
    confirming: "पुष्टि हो रही है…",
    cancel: "रद्द करें",
    cancelled: "कुछ नहीं बदला गया।",
    conversation: "बातचीत",
    empty: "शुरू करने के लिए कोई सवाल पूछें।",
    upload: {
      title: "ऐसा पर्चा जो आपके खाते में नहीं है",
      intro:
        "परिवार के किसी सदस्य का पर्चा, या काग़ज़ पर मिला पर्चा: उसकी फ़ोटो या PDF अपलोड करें, या नीचे छपा सत्यापन कोड लिखें।",
      privacy:
        "इसमें से सिर्फ़ MediEase कोड पढ़ा जाता है। जाँच के बाद फ़ाइल मिटा दी जाती है, और क्लिनिक का स्टाफ़ इसे कभी नहीं देखता। सहायक फ़ाइल नहीं, क्लिनिक का अपना रिकॉर्ड समझाता है।",
      file: "पर्चे की फ़ोटो या PDF",
      fileHelp: "PDF, JPEG या PNG, 10 MB तक। ध्यान रखें कि नीचे वाला चौकोर कोड फ़ोटो में आए।",
      send: "अपलोड करें",
      sending: "अपलोड हो रहा है…",
      or: "या",
      code: "सत्यापन कोड",
      codeHelp: "“सत्यापन कोड” के नीचे छपा कोड, जैसे 0192f3a4-7c1e-7b2a-9d40-5e6f7a8b9c0d।",
      verify: "कोड जाँचें",
      checking: "आपकी फ़ाइल जाँची जा रही है…",
      slow: "इसमें सामान्य से ज़्यादा समय लग रहा है। आप रुक सकते हैं, या कोड लिख सकते हैं।",
      challengeTitle: "मरीज़ की पुष्टि करें",
      challengeHelp:
        "यह पर्चा आपके खाते में नहीं है। मरीज़ के फ़ोन नंबर के आख़िरी 4 अंक लिखें, जैसे क्लिनिक के पास दर्ज हैं।",
      last4: "मरीज़ के फ़ोन के आख़िरी 4 अंक",
      check: "पुष्टि करें",
      attemptsLeft: (n) => `यह मेल नहीं खाया। ${n} कोशिश बाकी।`,
      verified: (doctor, clinic, day, version) => `सत्यापित: ${doctor}, ${clinic}, ${day} (संस्करण ${version})।`,
      representative: (until) => `आप ${until} तक इस पर्चे के बारे में पूछ सकते हैं। इसे आपके खाते में नहीं जोड़ा गया है।`,
      historical: (version, latest, latestDay) =>
        `यह पुराना संस्करण (संस्करण ${version}) है। डॉक्टर ने ${latestDay} को संस्करण ${latest} जारी किया। सहायक कौन-सा समझाए?`,
      chooseVersion: "कौन-सा संस्करण समझाना है",
      useUploaded: (version) => `जो मैंने अपलोड किया (संस्करण ${version}, पुराना)`,
      useLatest: (version) => `सबसे नया (संस्करण ${version})`,
      using: (version) => `सहायक संस्करण ${version} समझाएगा।`,
      asking: "सत्यापित पर्चे के बारे में पूछ रहे हैं।",
      remove: "हटाएँ",
      tryAgain: "दूसरी फ़ोटो लें या कोड लिखें।",
      rejected: {
        UPL_INFECTED: "सुरक्षा जाँच ने फ़ाइल को अस्वीकार किया और उसे मिटा दिया गया।",
        UPL_SCAN_UNAVAILABLE: "फ़ाइल अभी जाँची नहीं जा सकी और मिटा दी गई। कृपया बाद में फिर कोशिश करें।",
        UPL_NO_IDENTIFIER: "इसमें कोई MediEase कोड नहीं मिला। चौकोर कोड की साफ़ फ़ोटो लें, या कोड लिखें।",
        UPL_AMBIGUOUS: "इसमें एक से ज़्यादा पर्चे हैं। एक बार में एक पर्चा अपलोड करें।",
        UPL_UNREADABLE: "फ़ाइल पढ़ी नहीं जा सकी।",
        UPL_LOCKED: "बहुत सारी ग़लत कोशिशें। यह अपलोड रोक दिया गया है।",
        UPL_ABANDONED: "जाँच पूरी नहीं हुई और फ़ाइल मिटा दी गई।",
        UPL_EXPIRED: "इस जाँच का समय ख़त्म हो गया।",
        UPL_WITHDRAWN: "हटा दिया गया।",
        UPL_FILE_MISSING: "फ़ाइल नहीं मिली। कृपया फिर से अपलोड करें।",
      },
      rejectedOther: "यह पर्चा सत्यापित नहीं हो सका।",
    },
  },
  medicines: {
    title: "मेरी दवाइयाँ",
    views: "दिखाएँ",
    today: "आज",
    courses: "दवा के कोर्स",
    safety: "यह योजना सिर्फ़ आपके पर्चे को क्रम से दिखाती है। कुछ भी साफ़ न हो तो अपने डॉक्टर से पूछें।",
    contact: "अपने क्लिनिक से संपर्क करें",
    asWritten: "जैसा डॉक्टर ने लिखा",
    empty: "आपके पर्चों में अभी कोई दवा नहीं।",
    nothingOn: "इस दिन कोई दवा नहीं।",
    previousDay: "पिछला दिन",
    nextDay: "अगला दिन",
    backToToday: "आज",
    dayOf: (n, m) => `${m} में से दिन ${n}`,
    from: (date) => `${date} से`,
    until: (date) => `${date} तक`,
    by: (doctor, clinic) => `${doctor} · ${clinic}`,
    remindMe: (slot, time) => `मुझे याद दिलाएँ · ${slot} (${time})`,
    reminderTime: (slot) => `याद दिलाने का समय, ${slot}`,
    reminderOn: (time) => `${time} पर याद दिलाना चालू`,
    reminderSaved: "आपकी पसंद सहेज ली गई है।",
    saveTime: "समय सहेजें",
    doses: {
      taken: "ले ली",
      skipped: "नहीं ली",
      notRecorded: "दर्ज नहीं",
      upcoming: "आने वाली",
      takenAt: (time) => `${time} पर ले ली`,
      skippedAt: (time) => `${time} पर नहीं ली`,
      markAs: (state, medicine, slot) => `${state}: ${medicine}, ${slot}`,
      change: "बदलें",
      clear: "निशान हटाएँ",
      unsure: "अगर आपको समझ न आए कि क्या करें, तो अपने क्लिनिक से संपर्क करें।",
      history: "पिछला रिकॉर्ड",
      hideHistory: "रिकॉर्ड छिपाएँ",
      historyHeading: (version) => `पिछला रिकॉर्ड · संस्करण ${version}`,
      counts: (taken, skipped, notRecorded) => `ले ली ${taken} · नहीं ली ${skipped} · दर्ज नहीं ${notRecorded}`,
      saved: "सहेज लिया।",
      private: "आप यहाँ जो दर्ज करते हैं, वह सिर्फ़ आप देख सकते हैं। आपका क्लिनिक नहीं।",
    },
    remindersLater: "रिमाइंडर आपके चुने समय पर इस ऐप में सूचनाओं में दिखते हैं। अभी फ़ोन पर अलर्ट नहीं आता, इसलिए उन्हें देखने के लिए ऐप खोलें।",
    updated: "यह पर्चा बदला गया है — अपने रिमाइंडर फिर से चुनें।",
    noCourses: "अभी कोई कोर्स नहीं।",
  },
  account: {
    title: "खाता",
    times: "आपके दिन के समय",
    timesHelp: "इनसे आपकी दवाइयाँ घड़ी के समय पर दिखती हैं। इनसे आपका पर्चा कभी नहीं बदलता।",
    slots: { morning: "सुबह", afternoon: "दोपहर", evening: "शाम", night: "रात" },
    saveTimes: "समय सहेजें",
    timesSaved: "आपके दिन के समय सहेज लिए गए।",
    timesOrder: "हर समय पिछले वाले से बाद का हो, 05:00 से 23:30 के बीच।",
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
    unlinkConfirm: (clinic) => `${clinic} को हटाएँ? इसके अपॉइंटमेंट, पर्चे और रिमाइंडर आपके खाते से हट जाएँगे। क्लिनिक के अपने रिकॉर्ड बने रहेंगे।`,
    unlinkYes: "हाँ, हटाएँ",
    cancel: "रहने दें",
    unlinked: (clinic) => `${clinic} अब जुड़ा नहीं है।`,
    signOut: "साइन आउट",
    signingOut: "साइन आउट हो रहा है…",
  },
  link: {
    heading: (clinic) => `${clinic} के अपने रिकॉर्ड जोड़ें`,
    help: (clinic) => `${clinic} के आपके अपॉइंटमेंट, पर्चे और रिमाइंडर इस खाते में दिखेंगे। सिर्फ़ अपने रिकॉर्ड जोड़ें।`,
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
    rxHelp: "क्लिनिक के पास जो फ़ोन नंबर है, उसके आख़िरी 4 अंक लिखें। फिर उस क्लिनिक के आपके अपॉइंटमेंट, पर्चे और रिमाइंडर इस खाते में दिखेंगे।",
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
    PRT_DOSE_NOT_MARKABLE: "यह खुराक उसके दिन की शुरुआत से उसके समय के 48 घंटे बाद तक ही दर्ज की जा सकती है।",
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

/** The emailed-link pages (M6a-P4), shared with staff, who keep the English (M6b-P2 follow-up). */
export interface ForgotWords {
  readonly heading: string;
  readonly help: string;
  readonly sent: string;
  readonly email: string;
  readonly send: string;
  readonly sending: string;
  readonly back: string;
}

export interface ResetWords {
  readonly heading: string;
  readonly newPassword: string;
  readonly hint: string;
  readonly again: string;
  readonly tooShort: string;
  readonly different: string;
  readonly save: string;
  readonly saving: string;
  readonly newLink: string;
}

export interface VerifyWords {
  readonly heading: string;
  readonly help: string;
  readonly confirm: string;
  readonly confirming: string;
  readonly done: string;
  readonly goAccount: string;
}

export const FORGOT_EN: ForgotWords = {
  heading: "Reset your password",
  help: "Enter the email you sign in with and we will send you a link.",
  sent: "If an account uses that email, we have sent it a link to choose a new password. The link works once and lasts 30 minutes. Check your spam folder if it does not arrive.",
  email: "Email",
  send: "Send the link",
  sending: "Sending…",
  back: "Back to sign in",
};

export const RESET_EN: ResetWords = {
  heading: "Choose a new password",
  newPassword: "New password",
  hint: "At least 12 characters. Signing in elsewhere ends when you save.",
  again: "Type it again",
  tooShort: "Use at least 12 characters.",
  different: "The two passwords are not the same.",
  save: "Save the new password",
  saving: "Saving…",
  newLink: "Ask for a new link",
};

const VERIFY_EN: VerifyWords = {
  heading: "Confirm your email",
  help: "Press the button to confirm this is your email address.",
  confirm: "Confirm my email",
  confirming: "Confirming…",
  done: "Your email is confirmed. Thank you.",
  goAccount: "Go to your account",
};

const FORGOT_HI: ForgotWords = {
  heading: "अपना पासवर्ड बदलें",
  help: "जिस ईमेल से आप साइन इन करते हैं वह लिखें, हम आपको एक लिंक भेजेंगे।",
  sent: "अगर किसी खाते में यह ईमेल है, तो हमने उस पर नया पासवर्ड चुनने का लिंक भेज दिया है। लिंक एक बार और 30 मिनट तक काम करेगा। न मिले तो स्पैम फ़ोल्डर देखें।",
  email: "ईमेल",
  send: "लिंक भेजें",
  sending: "भेज रहे हैं…",
  back: "साइन इन पर वापस जाएँ",
};

const RESET_HI: ResetWords = {
  heading: "नया पासवर्ड चुनें",
  newPassword: "नया पासवर्ड",
  hint: "कम से कम 12 अक्षर। सहेजते ही दूसरी जगहों का साइन इन ख़त्म हो जाएगा।",
  again: "फिर से लिखें",
  tooShort: "कम से कम 12 अक्षर लिखें।",
  different: "दोनों पासवर्ड एक जैसे नहीं हैं।",
  save: "नया पासवर्ड सहेजें",
  saving: "सहेज रहे हैं…",
  newLink: "नया लिंक माँगें",
};

const VERIFY_HI: VerifyWords = {
  heading: "अपने ईमेल की पुष्टि करें",
  help: "यह आपका ईमेल पता है, इसकी पुष्टि के लिए बटन दबाएँ।",
  confirm: "मेरे ईमेल की पुष्टि करें",
  confirming: "पुष्टि हो रही है…",
  done: "आपके ईमेल की पुष्टि हो गई। धन्यवाद।",
  goAccount: "अपने खाते पर जाएँ",
};

export function forgotWords(language: PortalLanguage): ForgotWords {
  return language === "hi" ? FORGOT_HI : FORGOT_EN;
}

export function resetWords(language: PortalLanguage): ResetWords {
  return language === "hi" ? RESET_HI : RESET_EN;
}

export function verifyWords(language: PortalLanguage): VerifyWords {
  return language === "hi" ? VERIFY_HI : VERIFY_EN;
}
