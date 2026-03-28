"use client";

import { useState, useEffect, useRef } from "react";
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

// ─── Feature cards data ─────────────────────────────────────────────────────

const features = [
  {
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#c9944a" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
        <polyline points="17 8 12 3 7 8" />
        <line x1="12" y1="3" x2="12" y2="15" />
      </svg>
    ),
    title: "Upload anything",
    desc: "Tax returns, recordings, client docs",
  },
  {
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#c9944a" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
      </svg>
    ),
    title: "Ask questions",
    desc: "Natural language, instant answers",
  },
  {
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#c9944a" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      </svg>
    ),
    title: "Stay compliant",
    desc: "§7216 tracking, audit-ready",
  },
];

// ─── Stats data ─────────────────────────────────────────────────────────────

const stats = [
  { value: 50, suffix: "+", label: "CPA firms" },
  { value: 10, suffix: "K+", label: "Documents" },
  { value: 98, suffix: "%", label: "Accuracy" },
];

// ─── Count-up hook ──────────────────────────────────────────────────────────

function useCountUp(target: number, duration: number = 2000, delay: number = 1200) {
  const [count, setCount] = useState(0);
  const hasRun = useRef(false);

  useEffect(() => {
    if (hasRun.current) return;
    hasRun.current = true;

    const timeout = setTimeout(() => {
      const start = performance.now();
      const animate = (now: number) => {
        const elapsed = now - start;
        const progress = Math.min(elapsed / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);
        setCount(Math.round(target * eased));
        if (progress < 1) requestAnimationFrame(animate);
      };
      requestAnimationFrame(animate);
    }, delay);

    return () => clearTimeout(timeout);
  }, [target, duration, delay]);

  return count;
}

// ─── Counter stats bar ──────────────────────────────────────────────────────

function StatsBar() {
  const counts = stats.map((s) => useCountUp(s.value));

  return (
    <div style={{ display: "flex", flexDirection: "row", alignItems: "center", marginTop: "1.5rem" }}>
      {stats.map((stat, i) => (
        <div key={stat.label} style={{ display: "flex", alignItems: "center" }}>
          {i > 0 && (
            <div style={{ width: 1, height: 24, background: "rgba(255,255,255,0.08)", margin: "0 16px", flexShrink: 0 }} />
          )}
          <div style={{ textAlign: "center" }}>
            <div style={{ fontFamily: "var(--font-serif), 'Cormorant Garamond', Georgia, serif", fontSize: "1.6rem", fontWeight: 600, color: "#f0ede6", lineHeight: 1 }}>
              {counts[i]}
              <span style={{ color: "#c9944a" }}>{stat.suffix}</span>
            </div>
            <div style={{ fontFamily: "var(--font-sans), 'Outfit', sans-serif", fontSize: "0.65rem", fontWeight: 300, color: "#8a8680", textTransform: "uppercase", letterSpacing: "0.1em", marginTop: 2 }}>
              {stat.label}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

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
        {/* Animated gradient orbs */}
        <div className="auth-orb1" />
        <div className="auth-orb2" />

        {/* Animated accent lines */}
        <svg
          style={{ position: "absolute", top: "15%", right: "5%", zIndex: 0, overflow: "visible" }}
          width="140"
          height="100"
          viewBox="0 0 140 100"
          aria-hidden="true"
        >
          <line
            className="auth-accent-line auth-accent-line1"
            x1="0" y1="60" x2="120" y2="0"
            stroke="rgba(201,148,74,0.15)"
            strokeWidth="1"
          />
          <line
            className="auth-accent-line auth-accent-line2"
            x1="30" y1="95" x2="90" y2="50"
            stroke="rgba(201,148,74,0.12)"
            strokeWidth="1"
          />
        </svg>

        {/* Decorative diagonal lines */}
        <svg
          className="pointer-events-none absolute inset-0 h-full w-full"
          aria-hidden="true"
        >
          <line x1="70%" y1="0" x2="30%" y2="100%" stroke="rgba(201,148,74,0.06)" strokeWidth="1" />
          <line x1="80%" y1="0" x2="40%" y2="100%" stroke="rgba(201,148,74,0.04)" strokeWidth="1" />
          <line x1="90%" y1="0" x2="50%" y2="100%" stroke="rgba(201,148,74,0.03)" strokeWidth="1" />
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

            {/* Feature cards */}
            <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: "1.8rem" }}>
              {features.map((f, i) => (
                <div
                  key={f.title}
                  style={{
                    display: "flex", flexDirection: "row", alignItems: "center", gap: 12,
                    background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.04)",
                    borderRadius: 8, padding: "12px 14px",
                    opacity: 0, animation: `fadeUp 0.6s ease-out ${0.65 + i * 0.1}s forwards`,
                  }}
                >
                  <div style={{ width: 32, height: 32, borderRadius: "50%", background: "rgba(201,148,74,0.1)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                    {f.icon}
                  </div>
                  <div>
                    <div style={{ fontFamily: "var(--font-sans), 'Outfit', sans-serif", fontSize: "0.82rem", fontWeight: 500, color: "#f0ede6", marginBottom: 2 }}>
                      {f.title}
                    </div>
                    <div style={{ fontFamily: "var(--font-sans), 'Outfit', sans-serif", fontSize: "0.7rem", fontWeight: 300, color: "#8a8680" }}>
                      {f.desc}
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <div className="auth-rule anim-fade-up" style={{ animationDelay: "0.95s" }} />

            {/* Counter stats bar */}
            <div className="anim-fade-up" style={{ animationDelay: "1.05s" }}>
              <StatsBar />
            </div>
          </div>
        </div>

        {/* Bottom tagline */}
        <div className="relative z-10 p-8 anim-fade-up" style={{ animationDelay: "1.15s" }}>
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

        {/* Feature cards on mobile */}
        <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: "1.8rem" }}>
          {features.map((f) => (
            <div
              key={f.title}
              style={{
                display: "flex", flexDirection: "row", alignItems: "center", gap: 12,
                background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.04)",
                borderRadius: 8, padding: "12px 14px",
              }}
            >
              <div style={{ width: 32, height: 32, borderRadius: "50%", background: "rgba(201,148,74,0.1)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                {f.icon}
              </div>
              <div>
                <div style={{ fontFamily: "var(--font-sans), 'Outfit', sans-serif", fontSize: "0.82rem", fontWeight: 500, color: "#f0ede6", marginBottom: 2 }}>
                  {f.title}
                </div>
                <div style={{ fontFamily: "var(--font-sans), 'Outfit', sans-serif", fontSize: "0.7rem", fontWeight: 300, color: "#8a8680" }}>
                  {f.desc}
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="auth-rule" style={{ marginTop: "1rem" }} />
        <StatsBar />
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
          from { opacity: 0; }
          to { opacity: 1; }
        }

        @keyframes drift1 {
          0%, 100% { transform: translate(0, 0); }
          25% { transform: translate(20px, -15px); }
          50% { transform: translate(-10px, 20px); }
          75% { transform: translate(15px, 10px); }
        }

        @keyframes drift2 {
          0%, 100% { transform: translate(0, 0); }
          33% { transform: translate(-15px, 20px); }
          66% { transform: translate(20px, -10px); }
        }

        @keyframes drawLine {
          to { stroke-dashoffset: 0; }
        }

        .anim-fade-up {
          opacity: 0;
          animation: fadeUp 0.6s ease-out forwards;
        }

        .anim-fade-in {
          opacity: 0;
          animation: fadeIn 0.6s ease-out forwards;
        }

        /* ── Orbs ─────────────────────────────────────────────────────────── */

        .auth-orb1 {
          position: absolute;
          width: 350px;
          height: 350px;
          border-radius: 50%;
          background: radial-gradient(circle, rgba(201,148,74,0.07) 0%, transparent 70%);
          top: 10%;
          right: -10%;
          z-index: 0;
          animation: drift1 20s ease-in-out infinite;
          pointer-events: none;
        }

        .auth-orb2 {
          position: absolute;
          width: 250px;
          height: 250px;
          border-radius: 50%;
          background: radial-gradient(circle, rgba(201,148,74,0.04) 0%, transparent 70%);
          bottom: 20%;
          left: -5%;
          z-index: 0;
          animation: drift2 25s ease-in-out infinite;
          pointer-events: none;
        }

        /* ── Accent lines ─────────────────────────────────────────────────── */

        .auth-accent-line {
          stroke-dasharray: 120;
          stroke-dashoffset: 120;
          animation: drawLine 1.5s ease forwards;
        }

        .auth-accent-line1 {
          animation-delay: 0.8s;
        }

        .auth-accent-line2 {
          stroke-dasharray: 70;
          stroke-dashoffset: 70;
          animation-delay: 1.0s;
        }

        /* ── Left panel ───────────────────────────────────────────────────── */

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

        /* ── Gold rule ────────────────────────────────────────────────────── */

        .auth-rule {
          width: 40px;
          height: 1px;
          background: #c9944a;
          margin-top: 1.8rem;
        }

        /* ── Bottom & utility ─────────────────────────────────────────────── */

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
