import type { ReactNode } from "react";

import { SessionProvider } from "@/features/auth/SessionProvider";

/**
 * Everything under (clinic) needs a signed-in person. The provider asks the API
 * who that is (the session tokens are HttpOnly, and `me_access` is not sent on
 * page navigations), and sends anyone else to /sign-in. See M1-P6 design,
 * concept 2.
 */
export default function ClinicLayout({ children }: Readonly<{ children: ReactNode }>) {
  return <SessionProvider>{children}</SessionProvider>;
}
