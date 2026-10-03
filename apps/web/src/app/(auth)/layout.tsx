import type { ReactNode } from "react";

export default function AuthLayout({ children }: Readonly<{ children: ReactNode }>) {
  return <main className="flex min-h-screen items-start justify-center pt-12">{children}</main>;
}
