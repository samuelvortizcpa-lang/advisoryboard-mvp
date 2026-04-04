"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useEffect, useState } from "react";

/**
 * Extension auth callback page.
 *
 * Flow:
 * 1. Extension opens /extension-auth-callback directly
 * 2a. If signed in: page gets JWT from Clerk, puts it in the URL as ?token=JWT
 * 2b. If not signed in: redirects to /sign-in?redirect_url=/extension-auth-callback
 *     → user signs in → Clerk redirects back here → goes to 2a
 * 3. Service worker detects the URL with ?token=, extracts token, closes the tab
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

    const isRefresh = params.get("refresh") === "true";
    const isOffscreen = params.get("offscreen") === "true";

    if (!isSignedIn) {
      if (isRefresh) {
        // Silent refresh from extension — don't redirect to sign-in,
        // just signal failure so the extension knows the session is gone.
        setStatus("error");
        setErrorMsg("Session expired. Please sign in again.");
        return;
      }
      // Interactive sign-in: redirect to sign-in, which sends user back here
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

        // If loaded in an iframe (offscreen document case), postMessage the token
        // to the parent frame and skip the rest of the UI flow.
        if (isOffscreen && window !== window.top) {
          window.parent.postMessage({ type: 'CALLWEN_TOKEN', token }, '*');
          return;
        }

        // Update the URL so the content script can detect ?token= and relay it
        // to the service worker. Using replaceState avoids a full page reload
        // (which would destroy and re-inject the content script).
        window.history.replaceState(
          {},
          "",
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
              This may take a moment.
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
              You can close this tab.
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
            <Link
              href="/sign-in?redirect_url=/extension-auth-callback"
              style={{
                display: "inline-block",
                marginTop: 16,
                padding: "10px 20px",
                background: "#c9944a",
                color: "#fff",
                borderRadius: 8,
                fontWeight: 600,
                fontSize: 13,
                textDecoration: "none",
              }}
            >
              Try again
            </Link>
          </>
        )}
      </div>

      <style dangerouslySetInnerHTML={{
        __html: `@keyframes spin { to { transform: rotate(360deg); } }`,
      }} />
    </div>
  );
}
