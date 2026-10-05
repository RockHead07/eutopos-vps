import { Plus_Jakarta_Sans } from "next/font/google";
import Link from "@/lib/Link";
import { Icon } from "@/lib/Icon";
import { Nav } from "./nav";
import { Rail } from "./rail";
import "./globals.css";
import { cn } from "@/lib/utils";

// Diunduh saat build lalu disajikan dari server sendiri (tanpa panggilan ke Google saat dibuka).
const sans = Plus_Jakarta_Sans({ subsets: ["latin"], variable: "--font-sans" });

export const metadata = { title: "eutopos", description: "Map builds and versions for the eutopos VPS" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={cn("font-sans", sans.variable)}>
      <body>
        <Rail />
        <header className="topbar">
          <Link href="/" className="brand"><Icon name="logo" />eutopos</Link>
          <Nav />
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
