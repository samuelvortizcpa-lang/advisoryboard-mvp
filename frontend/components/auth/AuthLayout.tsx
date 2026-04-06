"use client";

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
  bgDeep: "#0e0d0c",
  bgRight: "#111110",
  accent: "#c9944a",
  accentLight: "#d4a85c",
  white: "#f0ede6",
  dim: "#a09a92",
  faint: "#6b6560",
  serif: "var(--font-serif), 'Cormorant Garamond', Georgia, serif",
  sans: "var(--font-sans), 'Outfit', sans-serif",
} as const;

// ─── Feature pills data ─────────────────────────────────────────────────────

const features = [
  {
    icon: (
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke={t.accent} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
        <polyline points="17 8 12 3 7 8" />
        <line x1="12" y1="3" x2="12" y2="15" />
      </svg>
    ),
    title: "Upload anything",
  },
  {
    icon: (
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke={t.accent} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      </svg>
    ),
    title: "Ask questions",
  },
  {
    icon: (
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke={t.accent} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      </svg>
    ),
    title: "Stay compliant",
  },
];


// ─── Animation helper ───────────────────────────────────────────────────────

function anim(delay: string): React.CSSProperties {
  return { opacity: 0, animation: `fadeUp 0.7s ease ${delay} forwards` };
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
    colorBackground: "#161514",
    colorText: t.white,
    colorTextSecondary: t.dim,
    colorInputBackground: "#1a1918",
    colorInputText: t.white,
    borderRadius: "10px",
    fontFamily: "'Outfit', -apple-system, sans-serif",
    fontSize: "0.9rem",
  },
  elements: {
    card: {
      backgroundColor: "#161514",
      border: "none",
      borderRadius: "14px",
      boxShadow: "none",
    },
    headerTitle: {
      fontFamily: "'Cormorant Garamond', Georgia, serif",
      fontSize: "1.6rem",
      fontWeight: "600",
      color: t.white,
    },
    headerSubtitle: {
      color: t.dim,
      fontWeight: "300",
    },
    socialButtonsBlockButton: {
      backgroundColor: "rgba(255,255,255,0.08)",
      border: "1px solid rgba(255,255,255,0.15)",
      color: t.white,
      fontWeight: "400",
      "&:hover": {
        backgroundColor: "rgba(255,255,255,0.12)",
        borderColor: "rgba(201,148,74,0.3)",
      },
    },
    formFieldInput: {
      backgroundColor: "#1a1918",
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
    dividerText: { color: t.faint },
    formFieldLabel: { color: t.dim, fontWeight: "400" },
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
    <div className={`${cormorant.variable} ${outfit.variable}`}>
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
        @keyframes drift3 {
          0%, 100% { transform: translate(0, 0); }
          50% { transform: translate(-25px, 15px); }
        }
        @keyframes drawLine {
          to { stroke-dashoffset: 0; }
        }
      `}} />

      <div className="flex flex-col lg:flex-row min-h-screen">
        {/* ── Left branding panel ────────────────────────────────────────── */}
        <div
          className="relative overflow-hidden lg:w-[48%] flex-shrink-0"
          style={{
            background: t.bgDeep,
            minHeight: "100vh",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "0 clamp(2rem, 5vw, 5rem)",
          }}
        >
          {/* Gradient orbs */}
          <div
            style={{
              position: "absolute",
              width: 450,
              height: 450,
              borderRadius: "50%",
              background: "radial-gradient(circle, rgba(201,148,74,0.08) 0%, transparent 70%)",
              top: "-5%",
              right: "-10%",
              zIndex: 0,
              animation: "drift1 22s ease-in-out infinite",
              pointerEvents: "none",
            }}
          />
          <div
            style={{
              position: "absolute",
              width: 350,
              height: 350,
              borderRadius: "50%",
              background: "radial-gradient(circle, rgba(201,148,74,0.05) 0%, transparent 70%)",
              bottom: "10%",
              left: "-8%",
              zIndex: 0,
              animation: "drift2 28s ease-in-out infinite",
              pointerEvents: "none",
            }}
          />
          <div
            style={{
              position: "absolute",
              width: 300,
              height: 300,
              borderRadius: "50%",
              background: "radial-gradient(circle, rgba(100,80,60,0.06) 0%, transparent 70%)",
              top: "40%",
              right: "20%",
              zIndex: 0,
              animation: "drift3 30s ease-in-out infinite",
              pointerEvents: "none",
            }}
          />

          {/* Noise texture */}
          <div
            style={{
              position: "absolute",
              inset: 0,
              opacity: 0.015,
              pointerEvents: "none",
              zIndex: 1,
              backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")`,
              backgroundRepeat: "repeat",
              backgroundSize: "128px 128px",
            }}
          />

          {/* Accent lines — top right */}
          <svg
            style={{ position: "absolute", top: "12%", right: "8%", zIndex: 1, overflow: "visible" }}
            width="160"
            height="120"
            viewBox="0 0 160 120"
            aria-hidden="true"
          >
            <line
              x1="0" y1="80" x2="140" y2="0"
              stroke="rgba(201,148,74,0.06)"
              strokeWidth="1"
              style={{
                strokeDasharray: 160,
                strokeDashoffset: 160,
                animation: "drawLine 3s ease 0.5s forwards",
              }}
            />
            <line
              x1="40" y1="110" x2="110" y2="55"
              stroke="rgba(201,148,74,0.04)"
              strokeWidth="1"
              style={{
                strokeDasharray: 90,
                strokeDashoffset: 90,
                animation: "drawLine 3s ease 0.8s forwards",
              }}
            />
          </svg>

          {/* Accent lines — bottom left */}
          <svg
            style={{ position: "absolute", bottom: "8%", left: "5%", zIndex: 1, overflow: "visible" }}
            width="120"
            height="80"
            viewBox="0 0 120 80"
            aria-hidden="true"
          >
            <line
              x1="120" y1="0" x2="0" y2="70"
              stroke="rgba(201,148,74,0.04)"
              strokeWidth="1"
              style={{
                strokeDasharray: 140,
                strokeDashoffset: 140,
                animation: "drawLine 3s ease 1.0s forwards",
              }}
            />
          </svg>

          {/* Decorative diagonal lines */}
          <svg
            className="pointer-events-none absolute inset-0 h-full w-full"
            style={{ zIndex: 0 }}
            aria-hidden="true"
          >
            <line x1="70%" y1="0" x2="30%" y2="100%" stroke="rgba(201,148,74,0.04)" strokeWidth="1" />
            <line x1="85%" y1="0" x2="45%" y2="100%" stroke="rgba(201,148,74,0.025)" strokeWidth="1" />
          </svg>

          {/* Content block */}
          <div style={{ position: "relative", zIndex: 2, maxWidth: 480, width: "100%" }}>
            {/* Logo */}
            <div style={anim("0s")}>
              <Link
                href="https://callwen.com"
                style={{
                  fontFamily: t.serif,
                  fontSize: "2rem",
                  fontWeight: 600,
                  color: t.white,
                  textDecoration: "none",
                  letterSpacing: "-0.01em",
                }}
              >
                Call<span style={{ color: t.accent }}>wen</span>
              </Link>
            </div>

            {/* Overline */}
            <p
              style={{
                fontFamily: t.sans,
                fontSize: "0.8rem",
                fontWeight: 500,
                letterSpacing: "0.25em",
                textTransform: "uppercase",
                color: t.accent,
                opacity: 0.7,
                marginTop: "2.5rem",
                marginBottom: "0.75rem",
                ...anim("0.1s"),
              }}
            >
              AI DOCUMENT INTELLIGENCE
            </p>

            {/* Headline */}
            <h1
              style={{
                fontFamily: t.serif,
                fontSize: "clamp(2.8rem, 5vw, 4rem)",
                fontWeight: 400,
                color: t.white,
                lineHeight: 1.15,
                marginBottom: "1.25rem",
                ...anim("0.2s"),
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
                fontSize: "1.05rem",
                fontWeight: 300,
                color: "#b8b3ab",
                maxWidth: 400,
                lineHeight: 1.6,
                ...anim("0.3s"),
              }}
            >
              Upload tax returns, meeting recordings, and client files. Ask
              questions. Get source-cited answers in seconds.
            </p>

            {/* Product preview — real dashboard screenshot */}
            <div
              className="hidden md:block"
              style={{
                marginTop: '2rem',
                maxWidth: '420px',
                opacity: 0,
                animation: 'fadeUp 0.7s ease forwards',
                animationDelay: '0.4s',
              }}
            >
              <div
                style={{
                  borderRadius: '12px',
                  overflow: 'hidden',
                  border: '1px solid rgba(255,255,255,0.08)',
                  boxShadow: '0 8px 32px rgba(0,0,0,0.4), 0 0 60px rgba(201,148,74,0.04)',
                  transform: 'perspective(800px) rotateY(-2deg)',
                  transition: 'transform 0.4s ease, box-shadow 0.4s ease',
                  position: 'relative' as const,
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.transform = 'perspective(800px) rotateY(0deg) scale(1.02)';
                  e.currentTarget.style.boxShadow = '0 12px 48px rgba(0,0,0,0.5), 0 0 80px rgba(201,148,74,0.08)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.transform = 'perspective(800px) rotateY(-2deg)';
                  e.currentTarget.style.boxShadow = '0 8px 32px rgba(0,0,0,0.4), 0 0 60px rgba(201,148,74,0.04)';
                }}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src="/dashboard-preview.png"
                  alt="Callwen dashboard preview"
                  style={{
                    width: '100%',
                    height: 'auto',
                    display: 'block',
                    filter: 'blur(0.5px) brightness(0.95)',
                  }}
                />
                {/* Subtle gradient overlay to blend with dark theme */}
                <div
                  style={{
                    position: 'absolute',
                    inset: 0,
                    background: 'linear-gradient(to bottom, rgba(14,13,12,0.05) 0%, rgba(14,13,12,0.15) 100%)',
                    pointerEvents: 'none',
                  }}
                />
              </div>
            </div>

            {/* Feature pills */}
            <div
              style={{
                display: 'flex',
                flexWrap: 'wrap',
                gap: 12,
                justifyContent: 'center',
                marginTop: '1.5rem',
                ...anim("0.55s"),
              }}
            >
              {features.map((f) => (
                <div
                  key={f.title}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 6,
                    padding: '6px 14px',
                    borderRadius: 99,
                    border: '1px solid rgba(201,148,74,0.15)',
                    background: 'rgba(201,148,74,0.05)',
                  }}
                >
                  <span style={{ display: 'flex', width: 12, height: 12 }}>
                    {f.icon}
                  </span>
                  <span
                    style={{
                      fontFamily: t.sans,
                      fontSize: '0.8rem',
                      color: t.accent,
                      fontWeight: 500,
                    }}
                  >
                    {f.title}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* ── Mobile condensed header (below lg when left panel is hidden) ── */}
        <div
          className="lg:hidden"
          style={{
            background: t.bgDeep,
            padding: "2.5rem 2rem 2rem",
          }}
        >
          <Link
            href="https://callwen.com"
            style={{
              fontFamily: t.serif,
              fontSize: "1.6rem",
              fontWeight: 600,
              color: t.white,
              textDecoration: "none",
            }}
          >
            Call<span style={{ color: t.accent }}>wen</span>
          </Link>

          <h1
            style={{
              fontFamily: t.serif,
              fontSize: "2rem",
              fontWeight: 400,
              color: t.white,
              lineHeight: 1.15,
              marginTop: 20,
            }}
          >
            Your documents, <em style={{ fontStyle: "italic", color: t.accentLight }}>unlocked.</em>
          </h1>

          <p
            style={{
              fontFamily: t.sans,
              fontSize: "0.95rem",
              fontWeight: 300,
              color: "#b8b3ab",
              lineHeight: 1.6,
              marginTop: 10,
            }}
          >
            Upload tax returns, meeting recordings, and client files.
          </p>
        </div>

        {/* ── Right auth panel ───────────────────────────────────────────── */}
        <div
          className="flex-1"
          style={{
            background: t.bgRight,
            minHeight: "100vh",
            display: "flex",
            flexDirection: "column",
            justifyContent: "center",
            alignItems: "center",
            padding: "3rem 1.5rem",
          }}
        >
          <div style={{ width: "100%", maxWidth: 480 }}>
            {/* Card wrapper around Clerk */}
            <div
              style={{
                border: "1px solid rgba(255,255,255,0.06)",
                borderRadius: 16,
                background: "rgba(255,255,255,0.02)",
                backdropFilter: "blur(20px)",
                WebkitBackdropFilter: "blur(20px)",
                boxShadow: "0 0 80px rgba(201,148,74,0.04), 0 4px 32px rgba(0,0,0,0.3)",
                padding: 4,
                opacity: 0,
                animation: "fadeUp 0.7s ease 0.3s forwards",
              }}
            >
              {children}
            </div>

            {/* Free to start */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 8,
                marginTop: 24,
                fontFamily: t.sans,
                fontSize: "0.85rem",
                fontWeight: 400,
                color: t.dim,
                opacity: 0,
                animation: "fadeUp 0.7s ease 0.5s forwards",
              }}
            >
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
                <circle cx="7" cy="7" r="6.5" stroke="#28c840" strokeWidth="1" />
                <path d="M4.5 7L6.5 9L10 5" stroke="#28c840" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <span>Free to start · No credit card required</span>
            </div>

            {/* Legal */}
            <p
              style={{
                fontFamily: t.sans,
                fontSize: "0.78rem",
                color: t.faint,
                textAlign: "center",
                maxWidth: 320,
                margin: "16px auto 0",
              }}
            >
              By continuing, you agree to our{" "}
              <Link href="/terms" style={{ color: t.faint, textDecoration: "none" }}>
                Terms of Service
              </Link>{" "}
              and{" "}
              <Link href="/privacy" style={{ color: t.faint, textDecoration: "none" }}>
                Privacy Policy
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
