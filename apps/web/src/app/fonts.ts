import localFont from "next/font/local";

/**
 * M7c-P7 (DESIGN.md §2): Manrope, self-hosted from this repository (OFL, ./fonts/Manrope-OFL.txt),
 * Latin only (25 KB, variable 200-800), served from our origin so the CSP's font-src 'self' holds.
 *
 * It is applied by the layouts of the clinic, ops, sign-in, apply and landing surfaces through
 * `BRAND_FONT`, never by the root layout: a patient page (`(patient)`) does not import it, so it
 * neither preloads nor downloads the font and stays inside its 200 KB budget (NFR-02, measured
 * 9 Nov 2026: the font pushed /portal/medicines to 230 KB). Patient pages use the system font.
 */
const manrope = localFont({
  src: "./fonts/manrope-latin-wght.woff2",
  weight: "200 800",
  style: "normal",
  display: "swap",
  variable: "--font-manrope",
});

/** Classes for a surface's outermost element: the font variable and the brand font stack. */
export const BRAND_FONT = `${manrope.variable} font-brand`;
