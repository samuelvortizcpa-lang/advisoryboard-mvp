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

// ─── Design tokens ──────────────────────────────────────────────────────────

const t = {
  bgDeep: "#0c0e13",
  bgMid: "#12151c",
  bgSurface: "#181c25",
  accent: "#c9944a",
  accentLight: "#e8b06a",
  white: "#f0ede6",
  whiteDim: "#8a8680",
  whiteFaint: "#4a4744",
  serif: "var(--font-serif), 'Cormorant Garamond', Georgia, serif",
  sans: "var(--font-sans), 'Outfit', sans-serif",
} as const;

// ─── Feature cards data ─────────────────────────────────────────────────────

const features = [
  {
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={t.accent} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
        <polyline points="17 8 12 3 7 8" />
        <line x1="12" y1="3" x2="12" y2="15" />
      </svg>
    ),
    title: "Upload anything",
    desc: "Tax returns, recordings, client docs",
  },
  {
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={t.accent} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      </svg>
    ),
    title: "Ask questions",
    desc: "Natural language, instant answers",
  },
  {
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={t.accent} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      </svg>
    ),
    title: "Stay compliant",
    desc: "\u00A77216 tracking, audit-ready",
  },
];

// ─── Stats data ─────────────────────────────────────────────────────────────

const stats = [
  { value: 50, suffix: "+", label: "CPA firms" },
  { value: 10, suffix: "K+", label: "Documents" },
  { value: 98, suffix: "%", label: "Accuracy" },
];

// ─── Count-up hook ──────────────────────────────────────────────────────────

function useCountUp(target: number, duration = 2000, delay = 1200) {
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
  const count0 = useCountUp(stats[0].value);
  const count1 = useCountUp(stats[1].value);
  const count2 = useCountUp(stats[2].value);
  const counts = [count0, count1, count2];

  return (
    <div style={{ display: "flex", alignItems: "center", marginTop: 18 }}>
      {stats.map((stat, i) => (
        <div key={stat.label} style={{ display: "flex", alignItems: "center" }}>
          {i > 0 && (
            <div
              style={{
                width: 1,
                height: 24,
                background: "rgba(255,255,255,0.08)",
                margin: "0 16px",
                flexShrink: 0,
              }}
            />
          )}
          <div style={{ textAlign: "center" }}>
            <div
              style={{
                fontFamily: t.serif,
                fontSize: "1.6rem",
                fontWeight: 600,
                color: t.white,
                lineHeight: 1,
              }}
            >
              {counts[i]}
              <span style={{ color: t.accent }}>{stat.suffix}</span>
            </div>
            <div
              style={{
                fontFamily: t.sans,
                fontSize: "0.65rem",
                fontWeight: 300,
                color: t.whiteDim,
                textTransform: "uppercase",
                letterSpacing: "0.1em",
                marginTop: 2,
              }}
            >
              {stat.label}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Feature card ───────────────────────────────────────────────────────────

function FeatureCard({
  icon,
  title,
  desc,
  delay,
}: {
  icon: React.ReactNode;
  title: string;
  desc: string;
  delay?: string;
}) {
  const animStyle = delay
    ? { opacity: 0 as number, animation: `fadeUp 0.7s ease ${delay} forwards` }
    : {};

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 12,
        background: "rgba(255,255,255,0.02)",
        border: "1px solid rgba(255,255,255,0.04)",
        borderRadius: 8,
        padding: "12px 14px",
        ...animStyle,
      }}
    >
      <div
        style={{
          width: 32,
          height: 32,
          borderRadius: "50%",
          background: "rgba(201,148,74,0.1)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
        }}
      >
        {icon}
      </div>
      <div>
        <div
          style={{
            fontFamily: t.sans,
            fontSize: "0.82rem",
            fontWeight: 500,
            color: t.white,
            marginBottom: 2,
          }}
        >
          {title}
        </div>
        <div
          style={{
            fontFamily: t.sans,
            fontSize: "0.7rem",
            fontWeight: 300,
            color: t.whiteDim,
          }}
        >
          {desc}
        </div>
      </div>
    </div>
  );
}

// ─── Animation helper ───────────────────────────────────────────────────────

function fadeUp(delay: string): React.CSSProperties {
  return { opacity: 0, animation: `fadeUp 0.7s ease ${delay} forwards` };
}

function fadeIn(delay: string): React.CSSProperties {
  return { opacity: 0, animation: `fadeIn 0.7s ease ${delay} forwards` };
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
    colorPrimary: t.accent,
    colorBackground: t.bgSurface,
    colorText: t.white,
    colorTextSecondary: t.whiteDim,
    colorInputBackground: "#1e222e",
    colorInputText: t.white,
    borderRadius: "8px",
    fontFamily: "'Outfit', -apple-system, sans-serif",
    fontSize: "0.9rem",
  },
  elements: {
    card: {
      backgroundColor: t.bgSurface,
      border: "1px solid rgba(255,255,255,0.06)",
      borderRadius: "12px",
      boxShadow: "0 8px 32px rgba(0,0,0,0.3)",
    },
    headerTitle: {
      fontFamily: "'Cormorant Garamond', Georgia, serif",
      fontSize: "1.6rem",
      fontWeight: "600",
      color: t.white,
    },
    headerSubtitle: {
      color: t.whiteDim,
      fontWeight: "300",
    },
    socialButtonsBlockButton: {
      backgroundColor: "#1e222e",
      border: "1px solid rgba(255,255,255,0.08)",
      color: t.white,
      fontWeight: "400",
      "&:hover": {
        backgroundColor: "#252a38",
        borderColor: "rgba(201,148,74,0.3)",
      },
    },
    formFieldInput: {
      backgroundColor: "#1e222e",
      border: "1px solid rgba(255,255,255,0.08)",
      color: t.white,
      "&:focus": {
        borderColor: t.accent,
        boxShadow: "0 0 0 2px rgba(201,148,74,0.15)",
      },
    },
    formButtonPrimary: {
      backgroundColor: t.accent,
      color: t.bgDeep,
      fontWeight: "500",
      "&:hover": { backgroundColor: t.accentLight },
    },
    footerActionLink: {
      color: t.accent,
      fontWeight: "400",
      "&:hover": { color: t.accentLight },
    },
    dividerLine: { backgroundColor: "rgba(255,255,255,0.06)" },
    dividerText: { color: t.whiteFaint },
    formFieldLabel: { color: t.whiteDim, fontWeight: "400" },
    identityPreviewEditButton: { color: t.accent },
    alert: {
      backgroundColor: "rgba(201,148,74,0.08)",
      border: "1px solid rgba(201,148,74,0.2)",
      color: t.accentLight,
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
    <div className={`${cormorant.variable} ${outfit.variable} flex min-h-screen`}>
      {/* Keyframes — plain <style>, NOT styled-jsx */}
      <style dangerouslySetInnerHTML={{ __html: `
        @keyframes fadeUp {
          from { opacity: 0; transform: translateY(20px); }
          to { opacity: 1; transform: translateY(0); }
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
      `}} />

      {/* ── Left branding panel ──────────────────────────────────────────── */}
      <div
        className="relative hidden w-[45%] flex-col justify-between overflow-hidden md:flex"
        style={{
          background: `${t.bgDeep} radial-gradient(ellipse at 50% 50%, rgba(201,148,74,0.03) 0%, transparent 70%)`,
        }}
      >
        {/* Gradient orbs */}
        <div
          style={{
            position: "absolute",
            width: 350,
            height: 350,
            borderRadius: "50%",
            background: "radial-gradient(circle, rgba(201,148,74,0.07) 0%, transparent 70%)",
            top: "10%",
            right: "-10%",
            zIndex: 0,
            animation: "drift1 20s ease-in-out infinite",
            pointerEvents: "none",
          }}
        />
        <div
          style={{
            position: "absolute",
            width: 250,
            height: 250,
            borderRadius: "50%",
            background: "radial-gradient(circle, rgba(201,148,74,0.04) 0%, transparent 70%)",
            bottom: "20%",
            left: "-5%",
            zIndex: 0,
            animation: "drift2 25s ease-in-out infinite",
            pointerEvents: "none",
          }}
        />

        {/* Accent lines */}
        <svg
          style={{ position: "absolute", top: "15%", right: "5%", zIndex: 0, overflow: "visible" }}
          width="140"
          height="100"
          viewBox="0 0 140 100"
          aria-hidden="true"
        >
          <line
            x1="0" y1="60" x2="120" y2="0"
            stroke="rgba(201,148,74,0.15)"
            strokeWidth="1"
            style={{
              strokeDasharray: 120,
              strokeDashoffset: 120,
              animation: "drawLine 1.5s ease 0.8s forwards",
            }}
          />
          <line
            x1="30" y1="95" x2="90" y2="50"
            stroke="rgba(201,148,74,0.12)"
            strokeWidth="1"
            style={{
              strokeDasharray: 70,
              strokeDashoffset: 70,
              animation: "drawLine 1.5s ease 1.0s forwards",
            }}
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
        <div className="relative z-10 p-8" style={fadeUp("0.1s")}>
          <Link
            href="https://callwen.com"
            style={{
              fontFamily: t.serif,
              fontSize: "1.8rem",
              fontWeight: 600,
              color: t.white,
              textDecoration: "none",
              letterSpacing: "-0.01em",
            }}
          >
            Call<span style={{ color: t.accent }}>wen</span>
          </Link>
        </div>

        {/* Center content */}
        <div className="relative z-10 flex-1 flex items-start px-8 lg:px-12" style={{ paddingTop: "6vh" }}>
          <div>
            {/* Overline */}
            <p
              style={{
                fontFamily: t.sans,
                fontSize: "0.7rem",
                fontWeight: 500,
                letterSpacing: "0.3em",
                textTransform: "uppercase",
                color: t.accent,
                marginBottom: "1rem",
                ...fadeUp("0.25s"),
              }}
            >
              AI DOCUMENT INTELLIGENCE
            </p>

            {/* Headline */}
            <h1
              style={{
                fontFamily: t.serif,
                fontSize: "3rem",
                fontWeight: 400,
                color: t.white,
                lineHeight: 1.15,
                ...fadeUp("0.4s"),
              }}
            >
              Your documents,
              <br />
              <em style={{ fontStyle: "italic", color: t.accentLight }}>unlocked.</em>
            </h1>

            {/* Subtitle */}
            <p
              style={{
                fontFamily: t.sans,
                fontSize: "0.95rem",
                fontWeight: 300,
                color: t.whiteDim,
                maxWidth: 380,
                lineHeight: 1.7,
                marginTop: "1rem",
                ...fadeUp("0.55s"),
              }}
            >
              Upload tax returns, meeting recordings, and client files. Ask
              questions. Get source-cited answers in seconds.
            </p>

            {/* Feature cards */}
            <div style={{ display: "flex", flexDirection: "column", gap: 7, marginTop: 20 }}>
              {features.map((f, i) => (
                <FeatureCard
                  key={f.title}
                  icon={f.icon}
                  title={f.title}
                  desc={f.desc}
                  delay={`${0.65 + i * 0.1}s`}
                />
              ))}
            </div>

            {/* Gold rule */}
            <div
              style={{
                width: 36,
                height: 1,
                background: t.accent,
                marginTop: 20,
                ...fadeUp("0.95s"),
              }}
            />

            {/* Counter stats */}
            <div style={fadeUp("1.05s")}>
              <StatsBar />
            </div>
          </div>
        </div>

        {/* Bottom tagline */}
        <div className="relative z-10 p-8" style={fadeUp("1.15s")}>
          <p style={{ fontFamily: t.sans, fontSize: "0.8rem", color: t.whiteFaint }}>
            Built by a CPA, for CPAs.
          </p>
        </div>
      </div>

      {/* ── Mobile header ────────────────────────────────────────────────── */}
      <div
        className="md:hidden"
        style={{ background: t.bgDeep, padding: "2rem 1.5rem 1.5rem" }}
      >
        <Link
          href="https://callwen.com"
          style={{
            fontFamily: t.serif,
            fontSize: "1.5rem",
            fontWeight: 600,
            color: t.white,
            textDecoration: "none",
          }}
        >
          Call<span style={{ color: t.accent }}>wen</span>
        </Link>

        <p
          style={{
            fontFamily: t.sans,
            fontSize: "0.7rem",
            fontWeight: 500,
            letterSpacing: "0.3em",
            textTransform: "uppercase",
            color: t.accent,
            marginTop: 24,
            marginBottom: 12,
          }}
        >
          AI DOCUMENT INTELLIGENCE
        </p>

        <h1
          style={{
            fontFamily: t.serif,
            fontSize: "1.8rem",
            fontWeight: 400,
            color: t.white,
            lineHeight: 1.15,
          }}
        >
          Your documents, <em style={{ fontStyle: "italic", color: t.accentLight }}>unlocked.</em>
        </h1>

        <p
          style={{
            fontFamily: t.sans,
            fontSize: "0.9rem",
            fontWeight: 300,
            color: t.whiteDim,
            lineHeight: 1.7,
            marginTop: 8,
          }}
        >
          Upload tax returns, meeting recordings, and client files. Ask
          questions. Get source-cited answers in seconds.
        </p>

        {/* Mobile feature cards */}
        <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 24 }}>
          {features.map((f) => (
            <FeatureCard key={f.title} icon={f.icon} title={f.title} desc={f.desc} />
          ))}
        </div>

        {/* Mobile gold rule */}
        <div style={{ width: 36, height: 1, background: t.accent, marginTop: 16 }} />

        {/* Mobile stats */}
        <StatsBar />
      </div>

      {/* ── Right auth panel ─────────────────────────────────────────────── */}
      <div
        className="flex min-h-screen flex-1 flex-col items-center justify-center px-6 py-12 md:min-h-0"
        style={{ background: t.bgMid }}
      >
        <div className="w-full max-w-[440px]" style={fadeIn("0.5s")}>
          {children}
        </div>

        {/* Free to start */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            marginTop: 24,
            fontFamily: t.sans,
            fontSize: "0.8rem",
            fontWeight: 400,
            color: t.whiteDim,
            ...fadeIn("0.7s"),
          }}
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
            <circle cx="7" cy="7" r="6.5" stroke={t.accent} strokeWidth="1" />
            <path d="M4.5 7L6.5 9L10 5" stroke={t.accent} strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span>Free to start · No credit card required</span>
        </div>

        {/* Legal */}
        <p
          style={{
            fontFamily: t.sans,
            fontSize: "0.75rem",
            color: t.whiteDim,
            textAlign: "center",
            maxWidth: 320,
            marginTop: 16,
          }}
        >
          By continuing, you agree to our{" "}
          <Link href="/terms" style={{ color: t.accent, textDecoration: "none" }}>
            Terms of Service
          </Link>{" "}
          and{" "}
          <Link href="/privacy" style={{ color: t.accent, textDecoration: "none" }}>
            Privacy Policy
          </Link>
        </p>
      </div>
    </div>
  );
}
