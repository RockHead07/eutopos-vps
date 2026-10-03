import Link from "next/link";
import "./globals.css";

export const metadata = { title: "eutopos" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <nav>
          <strong>eutopos</strong>
          <Link href="/">Jobs</Link>
          <Link href="/new/">New map session</Link>
          <Link href="/maps/">Map versions</Link>
        </nav>
        <main>{children}</main>
      </body>
    </html>
  );
}
