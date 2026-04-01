"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect, useState } from "react";

/**
 * Extension auth callback page.
 *
 * Flow:
 * 1. Extension opens /sign-in?redirect_url=/extension-auth-callback
 * 2. User signs in via Clerk
 * 3. Clerk redirects here (because of redirect_url)
 * 4. This page gets JWT from Clerk, puts it in the URL
 * 5. Service worker detects the URL, extracts token, closes the tab
 *
 * If the user arrives unauthenticated (e.g. direct visit), we redirect
 * to sign-in with redirect_url back to this page.
 */
export default function ExtensionAuthCallback() {
  const { isLoaded, isSignedIn, getToken } = useAuth();
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [errorMsg, setErrorMsg] = useState("");

  useEffect(() => {
    if (!isLoaded) return;

    // Already have a token in the URL — the service worker will pick it up.
    // Don't re-fetch; just show success.
    const params = new URLSearchParams(window.location.search);
    if (params.get("token")) {
      setStatus("success");
      return;
    }

    if (!isSignedIn) {
      // Redirect to sign-in, which will send the user back here after auth
      window.location.replace("/sign-in?redirect_url=/extension-auth-callback");
      return;
    }

    async function passTokenToExtension() {
      try {
        const token = await getToken();
        if (!token) {
          setStatus("error");
          setErrorMsg("Could not retrieve session token.");
          return;
        }

        // Replace the URL so the service worker can detect the token.
        // Using replace() avoids a back-button loop.
        window.location.replace(
          `/extension-auth-callback?token=${encodeURIComponent(token)}`
        );
        setStatus("success");
      } catch {
        setStatus("error");
        setErrorMsg("Failed to get authentication token.");
      }
    }

    passTokenToExtension();
  }, [isLoaded, isSignedIn, getToken]);

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "#f8fafc",
        color: "#1a202c",
        fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
      }}
    >
      <div style={{ textAlign: "center", maxWidth: 360, padding: 32 }}>
        {status === "loading" && (
          <>
            <div
              style={{
                width: 32,
                height: 32,
                border: "3px solid #e2e8f0",
                borderTopColor: "#14b8a6",
                borderRadius: "50%",
                animation: "spin 0.8s linear infinite",
                margin: "0 auto 16px",
              }}
            />
            <p style={{ fontSize: 15, fontWeight: 600 }}>Connecting to Callwen extension...</p>
            <p style={{ fontSize: 13, color: "#64748b", marginTop: 8 }}>
              This tab will close automatically.
            </p>
          </>
        )}

        {status === "success" && (
          <>
            <div
              style={{
                width: 32,
                height: 32,
                borderRadius: "50%",
                background: "#14b8a6",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                margin: "0 auto 16px",
                fontSize: 18,
                color: "#fff",
              }}
            >
              ✓
            </div>
            <p style={{ fontSize: 15, fontWeight: 600 }}>Connected!</p>
            <p style={{ fontSize: 13, color: "#64748b", marginTop: 8 }}>
              Passing credentials to the extension. This tab will close shortly.
            </p>
          </>
        )}

        {status === "error" && (
          <>
            <div
              style={{
                width: 32,
                height: 32,
                borderRadius: "50%",
                background: "#ef4444",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                margin: "0 auto 16px",
                fontSize: 18,
                color: "#fff",
              }}
            >
              ✕
            </div>
            <p style={{ fontSize: 15, fontWeight: 600 }}>Connection failed</p>
            <p style={{ fontSize: 13, color: "#64748b", marginTop: 8 }}>{errorMsg}</p>
            <a
              href="/sign-in?redirect_url=/extension-auth-callback"
              style={{
                display: "inline-block",
                marginTop: 16,
                padding: "10px 20px",
                background: "#14b8a6",
                color: "#fff",
                borderRadius: 8,
                fontWeight: 600,
                fontSize: 13,
                textDecoration: "none",
              }}
            >
              Try again
            </a>
          </>
        )}
      </div>

      <style dangerouslySetInnerHTML={{
        __html: `@keyframes spin { to { transform: rotate(360deg); } }`,
      }} />
    </div>
  );
}
