import type { Metadata } from "next";
import localFont from "next/font/local";
import { Providers } from "./providers";
import "./globals.css";

export const dynamic = 'force-dynamic';

const geistSans = localFont({
  src: "./fonts/GeistVF.woff",
  variable: "--font-geist-sans",
  weight: "100 900",
});
const geistMono = localFont({
  src: "./fonts/GeistMonoVF.woff",
  variable: "--font-geist-mono",
  weight: "100 900",
});

export const metadata: Metadata = {
  title: {
    default: "Callwen — AI Advisory Intelligence for CPA Firms",
    template: "%s — Callwen",
  },
  description: "Upload tax returns, meeting recordings, and client files. Ask questions across your entire document history. Get source-cited answers, tax strategy suggestions, and automated deadlines. Built by a CPA, for CPAs.",
  icons: {
    icon: "/icon.svg",
  },
  openGraph: {
    title: "Callwen — The AI that knows your clients as well as you do.",
    description: "AI-powered document intelligence for CPAs. Upload documents, ask questions, surface strategies. Free for 5 clients.",
    type: "website",
    url: "https://callwen.com",
    siteName: "Callwen",
  },
  twitter: {
    card: "summary_large_image",
    title: "Callwen — AI Advisory Intelligence for CPA Firms",
    description: "AI-powered document intelligence for CPAs. Upload documents, ask questions, surface strategies. Free for 5 clients.",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
