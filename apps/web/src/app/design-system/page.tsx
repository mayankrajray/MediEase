import type { Metadata } from "next";

import { BRAND_FONT } from "@/app/fonts";
import { Showcase } from "@/features/design-system/Showcase";

export const metadata: Metadata = {
  title: "Design system · MediEase",
  robots: { index: false, follow: false },
};

/** M7c-P7: the shared components in their states (DESIGN.md). Sample data only. */
export default function DesignSystemPage() {
  return (
    <div className={BRAND_FONT}>
      <Showcase />
    </div>
  );
}
