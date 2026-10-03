import { Plus_Jakarta_Sans } from "next/font/google";
import Link from "next/link";
import { Nav } from "./nav";
import "./globals.css";

// Diunduh saat build lalu disajikan dari server sendiri (tanpa panggilan ke Google saat dibuka).
const sans = Plus_Jakarta_Sans({ subsets: ["latin"], variable: "--font-sans" });

export const metadata = { title: "eutopos", description: "Map builds and versions for the eutopos VPS" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={sans.variable}>
      <body>
        <header className="topbar">
          <Link href="/" className="brand">eutopos</Link>
          <Nav />
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
