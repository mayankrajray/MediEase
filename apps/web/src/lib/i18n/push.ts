/**
 * M7e-E5 (spec web-push R50-R54): the words of the pop-up alerts switch, in English and Hindi. Apart
 * from the install prompts' words (pwa.ts), so pages that only offer the install stay light (NFR-02).
 */

import type { PwaLanguage } from "./pwa";

export interface DeviceWords {
  readonly title: string;
  readonly help: string;
  readonly checking: string;
  readonly on: string;
  readonly off: string;
  readonly turnOn: string;
  readonly turnOff: string;
  readonly turnedOn: string;
  readonly turnedOff: string;
  readonly blocked: string;
  readonly unsupported: string;
  readonly iosInstall: string;
  readonly notOffered: string;
  readonly tooMany: string;
}

const EN: DeviceWords = {
  title: "Pop-up alerts on this device",
  help: "A short alert on this phone or computer when there is news, even when MediEase is closed. It never shows names, times or medicines: open MediEase to see the details.",
  checking: "Checking this device…",
  on: "On for this device.",
  off: "Off for this device.",
  turnOn: "Turn on",
  turnOff: "Turn off",
  turnedOn: "Pop-up alerts are on for this device.",
  turnedOff: "Pop-up alerts are off for this device.",
  blocked: "This browser is blocking alerts from MediEase. Allow notifications for this site in the browser's settings, then try again.",
  unsupported: "This browser can't show alerts from MediEase. Try Chrome on Android, or the installed app.",
  iosInstall: "On iPhone and iPad, add MediEase to your Home Screen first, then turn alerts on in the app.",
  notOffered: "Pop-up alerts are not available yet.",
  tooMany: "Alerts are already on for 10 devices. Turn one off first.",
};

const HI: DeviceWords = {
  title: "इस डिवाइस पर पॉप-अप अलर्ट",
  help: "कोई नई जानकारी हो तो इस फ़ोन या कंप्यूटर पर छोटा अलर्ट, MediEase बंद हो तब भी। इसमें कभी नाम, समय या दवा नहीं दिखती: विवरण के लिए MediEase खोलें।",
  checking: "यह डिवाइस जाँच रहे हैं…",
  on: "इस डिवाइस के लिए चालू।",
  off: "इस डिवाइस के लिए बंद।",
  turnOn: "चालू करें",
  turnOff: "बंद करें",
  turnedOn: "इस डिवाइस पर पॉप-अप अलर्ट चालू हैं।",
  turnedOff: "इस डिवाइस पर पॉप-अप अलर्ट बंद हैं।",
  blocked: "यह ब्राउज़र MediEase के अलर्ट रोक रहा है। ब्राउज़र की सेटिंग में इस साइट के लिए सूचनाएँ चालू करें, फिर दोबारा कोशिश करें।",
  unsupported: "यह ब्राउज़र MediEase के अलर्ट नहीं दिखा सकता। Android पर Chrome या इंस्टॉल किया हुआ ऐप आज़माएँ।",
  iosInstall: "iPhone और iPad पर पहले MediEase को होम स्क्रीन पर जोड़ें, फिर ऐप में अलर्ट चालू करें।",
  notOffered: "पॉप-अप अलर्ट अभी उपलब्ध नहीं हैं।",
  tooMany: "10 डिवाइस पर अलर्ट पहले से चालू हैं। पहले किसी एक को बंद करें।",
};

export function deviceWords(language: PwaLanguage): DeviceWords {
  return language === "hi" ? HI : EN;
}
