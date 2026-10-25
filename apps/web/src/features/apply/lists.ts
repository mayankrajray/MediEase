/**
 * The published lists an application chooses from, and the reply promise (M6c-P1; spec
 * clinic-onboarding R4, R23, D3). They must equal the API's `domain/onboarding/lists.py` and
 * `REPLY_PROMISE`: an API test reads this file and fails when they differ.
 */

export const COUNCILS: readonly string[] = [
  "National Medical Commission",
  "Andhra Pradesh Medical Council",
  "Arunachal Pradesh Medical Council",
  "Assam Medical Council",
  "Bihar Council of Medical Registration",
  "Chhattisgarh Medical Council",
  "Delhi Medical Council",
  "Goa Medical Council",
  "Gujarat Medical Council",
  "Haryana Medical Council",
  "Himachal Pradesh Medical Council",
  "Jammu and Kashmir Medical Council",
  "Jharkhand Medical Council",
  "Karnataka Medical Council",
  "Madhya Pradesh Medical Council",
  "Maharashtra Medical Council",
  "Manipur Medical Council",
  "Meghalaya Medical Council",
  "Mizoram Medical Council",
  "Nagaland Medical Council",
  "Odisha Council of Medical Registration",
  "Punjab Medical Council",
  "Rajasthan Medical Council",
  "Sikkim Medical Council",
  "Tamil Nadu Medical Council",
  "Telangana State Medical Council",
  "Travancore-Cochin Medical Council (Kerala)",
  "Tripura State Medical Council",
  "Uttar Pradesh Medical Council",
  "Uttarakhand Medical Council",
  "West Bengal Medical Council",
];

export const SPECIALTIES: readonly string[] = [
  "General Medicine",
  "Family Medicine",
  "Paediatrics",
  "Obstetrics and Gynaecology",
  "Dermatology",
  "ENT",
  "Ophthalmology",
  "Orthopaedics",
  "Cardiology",
  "Diabetology",
  "Endocrinology",
  "Gastroenterology",
  "Neurology",
  "Nephrology",
  "Pulmonology",
  "Psychiatry",
  "Urology",
  "General Surgery",
];

/** D3: the same words on the form, the "Check your email" page and the "received" email. */
export const REPLY_PROMISE =
  "MediEase checks each doctor's registration by hand and will reply by email within 2 working days.";

export const MAX_DOCTORS = 10;
export const MAX_SPECIALTIES = 10;
export const MAX_CERTIFICATE_BYTES = 5 * 1024 * 1024;
export const MAX_SUBMISSION_BYTES = 30 * 1024 * 1024;
export const CERTIFICATE_ACCEPT = ".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png";
