import Link from "next/link";
import "./globals.css";

export const metadata = { title: "eutopos" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="id">
      <body>
        <nav>
          <strong>eutopos</strong>
          <Link href="/">Pekerjaan</Link>
          <Link href="/new/">Sesi peta baru</Link>
          <Link href="/maps/">Versi peta</Link>
        </nav>
        <main>{children}</main>
      </body>
    </html>
  );
}
