import type { Metadata } from "next";
import { Roboto, Roboto_Mono } from "next/font/google";
import "./globals.css";
import AppChrome from "@/components/AppChrome";

/**
 * Roboto at 400 and 500 only, at the owner's direction (Regular is the body weight).
 *
 * The two weights are not a shortcut — they are a constraint the type scale in `globals.css` §7
 * is written against, which is why no role there asks for 600. Adding a weight here without
 * changing that scale would load a face nothing uses; asking a role for a weight NOT listed here
 * would get a browser-synthesised faux-bold instead of a refusal, which is the failure mode
 * worth naming because it looks like a rendering bug rather than a missing font.
 */
const roboto = Roboto({
  subsets: ["latin", "vietnamese"],
  weight: ["400", "500"],
  variable: "--font-sans-loaded",
  display: "swap",
});

const robotoMono = Roboto_Mono({
  subsets: ["latin", "vietnamese"],
  weight: ["400", "500"],
  variable: "--font-mono-loaded",
  display: "swap",
});

// D-24: the description says what the tool shows, not how the model works. The previous version
// led with "tối đa hoá độ phủ trên ma trận tương đồng phần dư" — an accurate sentence about the
// method, in the one field that is a product description. The disclaimer stays: it is a claim
// about what this is NOT, which docs/02 §4 requires and which no reader should have to look for.
export const metadata: Metadata = {
  title: "Anchor Stock — Điểm neo đại diện thị trường cổ phiếu Việt Nam",
  description:
    "Theo dõi 85 cổ phiếu HOSE và 10 mã điểm neo đại diện: diễn biến phiên, biểu đồ kỹ thuật và nhóm cổ phiếu vận động cùng nhau. Không dự báo, không khuyến nghị đầu tư.",
};

/**
 * Restores the stored theme before the first paint.
 *
 * `next.config.ts` sets `output: "export"`, so every page is a static HTML file whose `<html>`
 * ships with `data-theme="light"` baked in. Restoring a stored "dark" from a `useEffect` would
 * therefore paint light first and correct itself after hydration — a white flash on every full
 * page load, which is exactly the complaint P11 set out to fix. This runs synchronously in
 * `<head>`, before the body exists.
 *
 * The `try/catch` is load-bearing: `localStorage` throws outright in a browser with site data
 * blocked. Failing silently leaves the `data-theme="light"` already in the markup, which is the
 * correct default anyway.
 */
const THEME_INIT = `try{var t=localStorage.getItem("theme");if(t==="dark"||t==="light"){document.documentElement.dataset.theme=t}}catch(e){}`;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="vi"
      data-theme="light"
      /* THEME_INIT deliberately rewrites this attribute before React hydrates, which is precisely
         the case this prop exists for: without it React reports the difference between the
         exported HTML ("light") and the restored choice ("dark") as a hydration error on every
         load. It suppresses the warning for THIS element's attributes only — children are still
         diffed normally. */
      suppressHydrationWarning
      className={`${roboto.variable} ${robotoMono.variable}`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT }} />
      </head>
      <body>
        <AppChrome>{children}</AppChrome>
      </body>
    </html>
  );
}
