import "./globals.css";
import type { Metadata } from "next";
import { Shell } from "./shell";

export const metadata: Metadata = {
  title: "Content OS",
  description: "YouTube pillar pipeline admin",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
