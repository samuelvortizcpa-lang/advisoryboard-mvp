"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { Cormorant_Garamond, Outfit } from "next/font/google";

// ─── Fonts ───────────────────────────────────────────────────────────────────

const cormorant = Cormorant_Garamond({
  subsets: ["latin"],
  weight: ["400", "600", "700"],
  style: ["normal", "italic"],
  variable: "--font-serif",
  display: "swap",
});

const outfit = Outfit({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600"],
  variable: "--font-sans",
  display: "swap",
});

// ─── Trust signals ──────────────────────────────────────────────────────────

const trustSignals = [
  "Trusted by 50+ CPA firms nationwide",
  "10,000+ documents analyzed and counting",
  "98% query accuracy with source citations",
  "Saving firms 15+ hours per week",
  "SOC 2 compliant infrastructure",
  "Join the fastest-growing AI platform for CPAs",
];

// ─── Clerk appearance config ─────────────────────────────────────────────────

export const clerkAppearance = {
  layout: {
    socialButtonsPlacement: "top" as const,
    socialButtonsVariant: "blockButton" as const,
    termsPageUrl: "/terms",
    privacyPageUrl: "/privacy",
  },
  variables: {
    colorPrimary: "#c9944a",
    colorBackground: "#181c25",
    colorText: "#f0ede6",
    colorTextSecondary: "#8a8680",
    colorInputBackground: "#1e222e",
    colorInputText: "#f0ede6",
    borderRadius: "8px",
    fontFamily: "'Outfit', -apple-system, sans-serif",
    fontSize: "0.9rem",
  },
  elements: {
    card: {
      backgroundColor: "#181c25",
      border: "1px solid rgba(255,255,255,0.06)",
      borderRadius: "12px",
      boxShadow: "0 8px 32px rgba(0,0,0,0.3)",
    },
    headerTitle: {
      fontFamily: "'Cormorant Garamond', Georgia, serif",
      fontSize: "1.6rem",
      fontWeight: "600",
      color: "#f0ede6",
    },
    headerSubtitle: {
      color: "#8a8680",
      fontWeight: "300",
    },
    socialButtonsBlockButton: {
      backgroundColor: "#1e222e",
      border: "1px solid rgba(255,255,255,0.08)",
      color: "#f0ede6",
      fontWeight: "400",
      "&:hover": {
        backgroundColor: "#252a38",
        borderColor: "rgba(201,148,74,0.3)",
      },
    },
    formFieldInput: {
      backgroundColor: "#1e222e",
      border: "1px solid rgba(255,255,255,0.08)",
      color: "#f0ede6",
      "&:focus": {
        borderColor: "#c9944a",
        boxShadow: "0 0 0 2px rgba(201,148,74,0.15)",
      },
    },
    formButtonPrimary: {
      backgroundColor: "#c9944a",
      color: "#0c0e13",
      fontWeight: "500",
      "&:hover": {
        backgroundColor: "#e8b06a",
      },
    },
    footerActionLink: {
      color: "#c9944a",
      fontWeight: "400",
      "&:hover": {
        color: "#e8b06a",
      },
    },
    dividerLine: {
      backgroundColor: "rgba(255,255,255,0.06)",
    },
    dividerText: {
      color: "#4a4744",
    },
    formFieldLabel: {
      color: "#8a8680",
      fontWeight: "400",
    },
    identityPreviewEditButton: {
      color: "#c9944a",
    },
    alert: {
      backgroundColor: "rgba(201,148,74,0.08)",
      border: "1px solid rgba(201,148,74,0.2)",
      color: "#e8b06a",
    },
  },
};

// ─── Rotating trust signal ──────────────────────────────────────────────────

function TrustSignal() {
  const [index, setIndex] = useState(0);
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    const interval = setInterval(() => {
      setVisible(false);
      setTimeout(() => {
        setIndex((prev) => (prev + 1) % trustSignals.length);
        setVisible(true);
      }, 500);
    }, 3500);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="auth-trust">
      <span className="auth-trust-dot">●</span>
      <span
        className="auth-trust-text"
        style={{ opacity: visible ? 1 : 0 }}
      >
        {trustSignals[index]}
      </span>
    </div>
  );
}

// ─── Component ───────────────────────────────────────────────────────────────

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div
      className={`${cormorant.variable} ${outfit.variable} flex min-h-screen`}
    >
      {/* ── Left branding panel ──────────────────────────────────────────── */}
      <div className="auth-left relative hidden w-[45%] flex-col justify-between overflow-hidden md:flex">
        {/* Decorative diagonal lines */}
        <svg
          className="pointer-events-none absolute inset-0 h-full w-full"
          aria-hidden="true"
        >
          <line
            x1="70%"
            y1="0"
            x2="30%"
            y2="100%"
            stroke="rgba(201,148,74,0.06)"
            strokeWidth="1"
          />
          <line
            x1="80%"
            y1="0"
            x2="40%"
            y2="100%"
            stroke="rgba(201,148,74,0.04)"
            strokeWidth="1"
          />
          <line
            x1="90%"
            y1="0"
            x2="50%"
            y2="100%"
            stroke="rgba(201,148,74,0.03)"
            strokeWidth="1"
          />
        </svg>

        {/* Logo */}
        <div className="relative z-10 p-8 anim-fade-up" style={{ animationDelay: "0.1s" }}>
          <Link href="https://callwen.com" className="auth-logo">
            Call<span>wen</span>
          </Link>
        </div>

        {/* Center content */}
        <div className="relative z-10 flex-1 flex items-center px-8 lg:px-12">
          <div>
            <p className="auth-overline anim-fade-up" style={{ animationDelay: "0.25s" }}>
              AI DOCUMENT INTELLIGENCE
            </p>
            <h1 className="auth-headline anim-fade-up" style={{ animationDelay: "0.4s" }}>
              Your documents,
              <br />
              <em>unlocked.</em>
            </h1>
            <p className="auth-subtitle anim-fade-up" style={{ animationDelay: "0.55s" }}>
              Upload tax returns, meeting recordings, and client files. Ask
              questions. Get source-cited answers in seconds.
            </p>
            <div className="auth-rule anim-fade-up" style={{ animationDelay: "0.7s" }} />
            <div className="anim-fade-up" style={{ animationDelay: "0.85s" }}>
              <TrustSignal />
            </div>
          </div>
        </div>

        {/* Bottom tagline */}
        <div className="relative z-10 p-8 anim-fade-up" style={{ animationDelay: "1.0s" }}>
          <p className="auth-tagline">Built by a CPA, for CPAs.</p>
        </div>
      </div>

      {/* ── Mobile header (visible below md) ─────────────────────────────── */}
      <div className="auth-mobile-header md:hidden">
        <Link href="https://callwen.com" className="auth-logo">
          Call<span>wen</span>
        </Link>
        <p className="auth-overline mt-6">AI DOCUMENT INTELLIGENCE</p>
        <h1 className="auth-headline auth-headline--mobile">
          Your documents, <em>unlocked.</em>
        </h1>
        <p className="auth-subtitle mt-2">
          Upload tax returns, meeting recordings, and client files. Ask
          questions. Get source-cited answers in seconds.
        </p>
        <div className="auth-rule" style={{ marginTop: "1rem" }} />
        <TrustSignal />
      </div>

      {/* ── Right auth panel ─────────────────────────────────────────────── */}
      <div className="auth-right flex min-h-screen flex-1 flex-col items-center justify-center px-6 py-12 md:min-h-0">
        <div className="w-full max-w-[440px] anim-fade-in" style={{ animationDelay: "0.5s" }}>
          {children}
        </div>

        <div className="auth-free-text anim-fade-in" style={{ animationDelay: "0.7s" }}>
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
            <circle cx="7" cy="7" r="6.5" stroke="#c9944a" strokeWidth="1" />
            <path d="M4.5 7L6.5 9L10 5" stroke="#c9944a" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span>Free to start · No credit card required</span>
        </div>

        <p className="auth-legal mt-4">
          By continuing, you agree to our{" "}
          <Link href="/terms">Terms of Service</Link> and{" "}
          <Link href="/privacy">Privacy Policy</Link>
        </p>
      </div>

      {/* ── Scoped styles ────────────────────────────────────────────────── */}
      <style jsx global>{`
        @keyframes fadeUp {
          from {
            opacity: 0;
            transform: translateY(16px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }

        @keyframes fadeIn {
          from {
            opacity: 0;
          }
          to {
            opacity: 1;
          }
        }

        .anim-fade-up {
          opacity: 0;
          animation: fadeUp 0.6s ease-out forwards;
        }

        .anim-fade-in {
          opacity: 0;
          animation: fadeIn 0.6s ease-out forwards;
        }

        .auth-left {
          background: #0c0e13;
          background-image: radial-gradient(
            ellipse at 50% 50%,
            rgba(201, 148, 74, 0.03) 0%,
            transparent 70%
          );
        }

        .auth-mobile-header {
          background: #0c0e13;
          padding: 2rem 1.5rem 1.5rem;
        }

        .auth-right {
          background: #12151c;
        }

        .auth-logo {
          font-family: var(--font-serif), "Cormorant Garamond", Georgia, serif;
          font-size: 1.8rem;
          font-weight: 600;
          color: #f0ede6;
          text-decoration: none;
          letter-spacing: -0.01em;
        }
        .auth-logo span {
          color: #c9944a;
        }

        .auth-overline {
          font-family: var(--font-sans), "Outfit", sans-serif;
          font-size: 0.7rem;
          font-weight: 500;
          letter-spacing: 0.3em;
          text-transform: uppercase;
          color: #c9944a;
          margin-bottom: 1rem;
        }

        .auth-headline {
          font-family: var(--font-serif), "Cormorant Garamond", Georgia, serif;
          font-size: 3rem;
          font-weight: 400;
          color: #f0ede6;
          line-height: 1.15;
        }
        .auth-headline--mobile {
          font-size: 1.8rem;
        }
        .auth-headline em {
          font-style: italic;
          color: #e8b06a;
        }

        .auth-subtitle {
          font-family: var(--font-sans), "Outfit", sans-serif;
          font-size: 0.95rem;
          font-weight: 300;
          color: #8a8680;
          max-width: 380px;
          line-height: 1.7;
          margin-top: 1.25rem;
        }

        .auth-rule {
          width: 40px;
          height: 1px;
          background: #c9944a;
          margin-top: 2rem;
        }

        .auth-trust {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          margin-top: 1.25rem;
          min-height: 1.5rem;
        }

        .auth-trust-dot {
          color: #c9944a;
          font-size: 0.5rem;
          flex-shrink: 0;
        }

        .auth-trust-text {
          font-family: var(--font-sans), "Outfit", sans-serif;
          font-size: 0.8rem;
          font-weight: 300;
          color: #f0ede6;
          transition: opacity 0.5s ease;
        }

        .auth-tagline {
          font-family: var(--font-sans), "Outfit", sans-serif;
          font-size: 0.8rem;
          color: #4a4744;
        }

        .auth-free-text {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          margin-top: 1.5rem;
          font-family: var(--font-sans), "Outfit", sans-serif;
          font-size: 0.8rem;
          font-weight: 400;
          color: #8a8680;
        }

        .auth-legal {
          font-family: var(--font-sans), "Outfit", sans-serif;
          font-size: 0.75rem;
          color: #8a8680;
          text-align: center;
          max-width: 320px;
        }
        .auth-legal a {
          color: #c9944a;
          text-decoration: none;
        }
        .auth-legal a:hover {
          color: #e8b06a;
        }
      `}</style>
    </div>
  );
}
