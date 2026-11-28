import type { Viewport } from "next";
import { Plus_Jakarta_Sans } from "next/font/google";
import Link from "@/lib/Link";
import { Icon } from "@/lib/Icon";
import { MobileNav, Nav } from "./nav";
import { Rail } from "./rail";
import { AccountMenu } from "./account";
import { Notifications } from "./notifications";
import { LocaleProvider } from "@/lib/i18n";
import { ThemeProvider } from "@/lib/theme";
import "./globals.css";
import { TooltipProvider } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

// Diunduh saat build lalu disajikan dari server sendiri (tanpa panggilan ke Google saat dibuka).
const sans = Plus_Jakarta_Sans({ subsets: ["latin"], variable: "--font-sans" });

export const metadata = { title: "eutopos", description: "Map builds and versions for the eutopos VPS" };

export const viewport: Viewport = { viewportFit: "cover" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="id" className={cn("font-sans", sans.variable)} suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `(function () {
              let theme;
              try { theme = localStorage.getItem("eutopos-theme"); } catch {}
              const dark = theme === "dark" ||
                (theme !== "light" && window.matchMedia("(prefers-color-scheme: dark)").matches);
              document.documentElement.classList.toggle("dark", dark);
              document.documentElement.style.colorScheme = dark ? "dark" : "light";

              // Bootstrap owns this tag so React does not reinsert a light version during hydration.
              const meta = document.createElement("meta");
              meta.name = "theme-color";
              meta.content = dark ? "#202225" : "#f4f7ee";
              document.head.appendChild(meta);
            })();`,
          }}
        />
      </head>
      <body>
        <ThemeProvider>
          <LocaleProvider>
            <TooltipProvider>
              <Rail />
              <header className="topbar">
                <Link href="/" className="brand"><Icon name="logo" />eutopos</Link>
                <Nav />
                <div className="ml-auto flex items-center gap-2">
                  <Notifications />
                  <AccountMenu />
                </div>
              </header>
              <main>{children}</main>
              <MobileNav />
            </TooltipProvider>
          </LocaleProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
