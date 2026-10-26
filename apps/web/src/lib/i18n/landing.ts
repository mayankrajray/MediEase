/**
 * Words for the landing page (`/`, M6c-P8; FR-LND-01, 02). English and Hindi. No clinical claims:
 * MediEase organises a clinic's work; it never advises on health. Prices are the PRD §12 pilot
 * hypothesis (`PLANS`), one place to change them.
 */

import type { PortalLanguage } from "./portal";

export interface Plan {
  readonly id: "solo" | "clinic" | "plus";
  readonly rupeesPerMonth: number;
}

/** PRD §12 (hypothesis to test): the developer confirms before the page is deployed. */
export const PLANS: readonly Plan[] = [
  { id: "solo", rupeesPerMonth: 499 },
  { id: "clinic", rupeesPerMonth: 999 },
  { id: "plus", rupeesPerMonth: 1499 },
];

export interface LandingWords {
  readonly title: string;
  readonly description: string;
  readonly nav: { readonly clinics: string; readonly patients: string; readonly pricing: string; readonly signIn: string };
  readonly hero: { readonly title: string; readonly body: string; readonly apply: string; readonly find: string };
  readonly problem: { readonly title: string; readonly points: readonly string[] };
  readonly clinics: {
    readonly title: string;
    readonly promise: string;
    readonly features: readonly { readonly title: string; readonly body: string }[];
    readonly roles: readonly { readonly title: string; readonly body: string }[];
    readonly rolesTitle: string;
    readonly apply: string;
    readonly demo: string;
  };
  readonly patients: { readonly title: string; readonly body: string; readonly find: string; readonly signIn: string; readonly emergency: string };
  readonly pricing: {
    readonly title: string;
    readonly note: string;
    readonly perMonth: string;
    readonly names: Readonly<Record<Plan["id"], string>>;
    readonly includes: Readonly<Record<Plan["id"], string>>;
    readonly trial: string;
    readonly noCommission: string;
  };
  readonly trust: { readonly title: string; readonly points: readonly string[] };
  readonly faq: { readonly title: string; readonly items: readonly { readonly q: string; readonly a: string }[] };
  readonly footer: { readonly staff: string; readonly apply: string; readonly find: string };
  readonly switchTo: string;
  readonly switchLabel: string;
}

const EN: LandingWords = {
  title: "MediEase · Run your clinic simply, let patients find you",
  description: "Appointments, queue, records and prescriptions for small clinics in India, and a directory where patients find verified doctors.",
  nav: { clinics: "For clinics", patients: "For patients", pricing: "Pricing", signIn: "Staff sign in" },
  hero: {
    title: "Your clinic, organised. Your patients, informed.",
    body: "MediEase runs appointments, the waiting queue, patient records and printed prescriptions for small clinics, and lets patients find verified doctors and ask for a time.",
    apply: "Apply to join MediEase",
    find: "Find a doctor",
  },
  problem: {
    title: "Why clinics move to MediEase",
    points: [
      "Patients call again and again to ask when it is their turn.",
      "Appointments live in a register, WhatsApp chats and memory.",
      "Old prescriptions are hard to find when a patient returns.",
    ],
  },
  clinics: {
    title: "For clinics",
    promise: "Once MediEase approves your application, your clinic is set up in about 5 minutes.",
    features: [
      { title: "Appointments and tokens", body: "Time slots or numbered tokens, walk-ins and a live queue patients can follow on their phone." },
      { title: "Records and prescriptions", body: "Each visit and prescription in one place, printed on your letterhead and shared as a private link." },
      { title: "Booking requests", body: "Patients ask for a time from your page; the front desk accepts, declines or suggests another." },
      { title: "Reminders", body: "Appointment and follow-up reminders, with the patient's consent." },
    ],
    rolesTitle: "A screen for each person",
    roles: [
      { title: "Owner", body: "Today's numbers, the team, the clinic's settings and the audit log." },
      { title: "Doctor", body: "My queue, my patients, the consultation and the prescription." },
      { title: "Front desk", body: "The queue, booking requests, registering and finding patients." },
    ],
    apply: "Apply to join MediEase",
    demo: "Apply, and we will call you to show MediEase in about 20 minutes.",
  },
  patients: {
    title: "For patients",
    body: "Find clinics and doctors whose registration MediEase has checked by hand, see their free times, and ask for one. The clinic replies in the app.",
    find: "Find a doctor",
    signIn: "Sign in to the patient app (Google or email)",
    emergency: "MediEase is not for emergencies. In an emergency call your local emergency number or go to the nearest hospital.",
  },
  pricing: {
    title: "Pricing",
    note: "Pilot prices. Every plan starts with a 14-day free trial, no card needed.",
    perMonth: "/ month",
    names: { solo: "Solo", clinic: "Clinic", plus: "Clinic Plus" },
    includes: {
      solo: "1 doctor and 1 staff member. Appointments, queue, records, prescriptions and a directory listing.",
      clinic: "Up to 3 doctors and 5 users. Everything in Solo.",
      plus: "Up to 5 doctors and unlimited staff. Everything in Clinic.",
    },
    trial: "14-day free trial",
    noCommission: "No commission and no fee per booking. WhatsApp messages are charged at cost on the same invoice.",
  },
  trust: {
    title: "Privacy and safety",
    points: [
      "Every doctor's registration is checked by a person at MediEase before the clinic goes live.",
      "Each clinic's records are kept apart from every other clinic's.",
      "Messages and links to patients carry no diagnosis or medicine names.",
      "MediEase never gives medical advice, shows ads or sells data.",
    ],
  },
  faq: {
    title: "Questions",
    items: [
      {
        q: "Who can join?",
        a: "Clinics and doctors with their own practice in India whose doctors are registered with the National Medical Commission or a state medical council.",
      },
      { q: "How long does approval take?", a: "MediEase checks each doctor's registration by hand and replies by email within 2 working days." },
      {
        q: "Do patients need an app?",
        a: "No. Prescriptions and the live queue open as links in the browser. Patients who want to ask for times create a free account.",
      },
      { q: "Can we stay out of the directory?", a: "Yes. Listing is the clinic's choice, and your own page link works either way." },
      { q: "Does MediEase suggest medicines or doses?", a: "Never. The doctor writes every prescription; MediEase only prints and shares it." },
    ],
  },
  footer: { staff: "Staff sign in", apply: "Apply to join", find: "Find a doctor" },
  switchTo: "हिंदी में देखें",
  switchLabel: "View this page in Hindi",
};

const HI: LandingWords = {
  title: "MediEase · क्लिनिक आसानी से चलाएँ, मरीज़ आपको ढूँढें",
  description: "भारत के छोटे क्लिनिकों के लिए अपॉइंटमेंट, कतार, रिकॉर्ड और पर्चे, और एक डायरेक्टरी जहाँ मरीज़ जाँचे गए डॉक्टर ढूँढते हैं।",
  nav: { clinics: "क्लिनिकों के लिए", patients: "मरीज़ों के लिए", pricing: "कीमत", signIn: "स्टाफ़ साइन इन" },
  hero: {
    title: "आपका क्लिनिक, व्यवस्थित। आपके मरीज़, जानकार।",
    body: "MediEase छोटे क्लिनिकों के अपॉइंटमेंट, इंतज़ार की कतार, मरीज़ों के रिकॉर्ड और छपे पर्चे संभालता है, और मरीज़ों को जाँचे गए डॉक्टर ढूँढकर समय माँगने देता है।",
    apply: "MediEase से जुड़ने के लिए आवेदन करें",
    find: "डॉक्टर खोजें",
  },
  problem: {
    title: "क्लिनिक MediEase क्यों अपनाते हैं",
    points: [
      "मरीज़ बार-बार फ़ोन करके पूछते हैं कि उनकी बारी कब है।",
      "अपॉइंटमेंट रजिस्टर, WhatsApp चैट और याददाश्त में बिखरे रहते हैं।",
      "मरीज़ लौटे तो पुराने पर्चे ढूँढना मुश्किल होता है।",
    ],
  },
  clinics: {
    title: "क्लिनिकों के लिए",
    promise: "MediEase आपका आवेदन मंज़ूर करे, तो आपका क्लिनिक लगभग 5 मिनट में तैयार हो जाता है।",
    features: [
      { title: "अपॉइंटमेंट और टोकन", body: "समय स्लॉट या नंबर वाले टोकन, बिना अपॉइंटमेंट आए मरीज़ और एक लाइव कतार जिसे मरीज़ फ़ोन पर देख सकें।" },
      { title: "रिकॉर्ड और पर्चे", body: "हर विज़िट और पर्चा एक जगह, आपके लेटरहेड पर छपा और निजी लिंक से भेजा गया।" },
      { title: "बुकिंग अनुरोध", body: "मरीज़ आपके पेज से समय माँगते हैं; फ़्रंट डेस्क मान लेता है, मना करता है या दूसरा समय सुझाता है।" },
      { title: "रिमाइंडर", body: "मरीज़ की सहमति से अपॉइंटमेंट और फ़ॉलो-अप के रिमाइंडर।" },
    ],
    rolesTitle: "हर व्यक्ति के लिए अपनी स्क्रीन",
    roles: [
      { title: "मालिक", body: "आज के आँकड़े, टीम, क्लिनिक की सेटिंग और ऑडिट लॉग।" },
      { title: "डॉक्टर", body: "मेरी कतार, मेरे मरीज़, परामर्श और पर्चा।" },
      { title: "फ़्रंट डेस्क", body: "कतार, बुकिंग अनुरोध, मरीज़ों का पंजीकरण और खोज।" },
    ],
    apply: "MediEase से जुड़ने के लिए आवेदन करें",
    demo: "आवेदन करें, हम आपको लगभग 20 मिनट में MediEase दिखाने के लिए फ़ोन करेंगे।",
  },
  patients: {
    title: "मरीज़ों के लिए",
    body: "ऐसे क्लिनिक और डॉक्टर खोजें जिनका पंजीकरण MediEase ने हाथ से जाँचा है, उनके खाली समय देखें और एक माँगें। क्लिनिक ऐप में जवाब देता है।",
    find: "डॉक्टर खोजें",
    signIn: "मरीज़ ऐप में साइन इन करें (Google या ईमेल)",
    emergency: "MediEase आपात स्थिति के लिए नहीं है। आपात स्थिति में अपने यहाँ का आपातकालीन नंबर मिलाएँ या सबसे नज़दीकी अस्पताल जाएँ।",
  },
  pricing: {
    title: "कीमत",
    note: "पायलट कीमतें। हर प्लान 14 दिन के मुफ़्त ट्रायल से शुरू होता है, कार्ड की ज़रूरत नहीं।",
    perMonth: "/ महीना",
    names: { solo: "सोलो", clinic: "क्लिनिक", plus: "क्लिनिक प्लस" },
    includes: {
      solo: "1 डॉक्टर और 1 स्टाफ़। अपॉइंटमेंट, कतार, रिकॉर्ड, पर्चे और डायरेक्टरी में जगह।",
      clinic: "3 डॉक्टर और 5 उपयोगकर्ता तक। सोलो का सब कुछ।",
      plus: "5 डॉक्टर तक और असीमित स्टाफ़। क्लिनिक का सब कुछ।",
    },
    trial: "14 दिन मुफ़्त ट्रायल",
    noCommission: "कोई कमीशन नहीं, हर बुकिंग पर कोई शुल्क नहीं। WhatsApp संदेश लागत पर उसी बिल में।",
  },
  trust: {
    title: "निजता और सुरक्षा",
    points: [
      "क्लिनिक शुरू होने से पहले MediEase का एक व्यक्ति हर डॉक्टर का पंजीकरण जाँचता है।",
      "हर क्लिनिक के रिकॉर्ड बाकी सभी क्लिनिकों से अलग रखे जाते हैं।",
      "मरीज़ों को जाने वाले संदेशों और लिंक में बीमारी या दवा का नाम नहीं होता।",
      "MediEase कभी चिकित्सा सलाह नहीं देता, विज्ञापन नहीं दिखाता और डेटा नहीं बेचता।",
    ],
  },
  faq: {
    title: "सवाल",
    items: [
      {
        q: "कौन जुड़ सकता है?",
        a: "भारत के क्लिनिक और अपनी प्रैक्टिस वाले डॉक्टर, जिनके डॉक्टर राष्ट्रीय चिकित्सा आयोग या किसी राज्य चिकित्सा परिषद में पंजीकृत हों।",
      },
      { q: "मंज़ूरी में कितना समय लगता है?", a: "MediEase हर डॉक्टर का पंजीकरण हाथ से जाँचता है और 2 कार्य दिवसों में ईमेल से जवाब देता है।" },
      {
        q: "क्या मरीज़ों को ऐप चाहिए?",
        a: "नहीं। पर्चे और लाइव कतार ब्राउज़र में लिंक की तरह खुलते हैं। जो मरीज़ समय माँगना चाहें, वे मुफ़्त खाता बनाते हैं।",
      },
      { q: "क्या हम डायरेक्टरी से बाहर रह सकते हैं?", a: "हाँ। डायरेक्टरी में आना क्लिनिक की मर्ज़ी है, और आपके पेज का लिंक दोनों हालत में चलता है।" },
      { q: "क्या MediEase दवा या खुराक सुझाता है?", a: "कभी नहीं। हर पर्चा डॉक्टर लिखते हैं; MediEase उसे सिर्फ़ छापता और भेजता है।" },
    ],
  },
  footer: { staff: "स्टाफ़ साइन इन", apply: "आवेदन करें", find: "डॉक्टर खोजें" },
  switchTo: "View in English",
  switchLabel: "इस पेज को अंग्रेज़ी में देखें",
};

export function landingWords(language: PortalLanguage): LandingWords {
  return language === "hi" ? HI : EN;
}
