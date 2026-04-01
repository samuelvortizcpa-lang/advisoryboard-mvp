"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect, useState } from "react";

/**
 * Extension auth callback page.
 *
 * When the Chrome extension triggers sign-in, Clerk redirects here after
 * authentication. This page grabs the session token from Clerk and passes
 * it back to the extension via a URL the service worker is watching:
 *   callwen.com/extension-auth-callback?token=<jwt>
 *
 * The service worker intercepts this URL in chrome.tabs.onUpdated, extracts
 * the token, stores it, and closes this tab automatically.
 */
export default function ExtensionAuthCallback() {
  const { isLoaded, isSignedIn, getToken } = useAuth();
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [errorMsg, setErrorMsg] = useState("");

  useEffect(() => {
    if (!isLoaded) return;

    async function passTokenToExtension() {
      if (!isSignedIn) {
        setStatus("error");
        setErrorMsg("Not signed in. Please sign in first.");
        return;
      }

      try {
        const token = await getToken();
        if (!token) {
          setStatus("error");
          setErrorMsg("Could not retrieve session token.");
          return;
        }

        // Redirect to the callback URL that the extension service worker watches.
        // The service worker will extract the token and close this tab.
        window.location.href = `/extension-auth-callback?token=${encodeURIComponent(token)}`;
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
        background: "#0f1419",
        color: "#e2e8f0",
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
                border: "3px solid #2d3748",
                borderTopColor: "#14b8a6",
                borderRadius: "50%",
                animation: "spin 0.8s linear infinite",
                margin: "0 auto 16px",
              }}
            />
            <p style={{ fontSize: 15, fontWeight: 600 }}>Connecting to Callwen extension...</p>
            <p style={{ fontSize: 13, color: "#94a3b8", marginTop: 8 }}>
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
              }}
            >
              ✓
            </div>
            <p style={{ fontSize: 15, fontWeight: 600 }}>Connected!</p>
            <p style={{ fontSize: 13, color: "#94a3b8", marginTop: 8 }}>
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
              }}
            >
              ✕
            </div>
            <p style={{ fontSize: 15, fontWeight: 600 }}>Connection failed</p>
            <p style={{ fontSize: 13, color: "#94a3b8", marginTop: 8 }}>{errorMsg}</p>
            <a
              href="/sign-in?extension=true"
              style={{
                display: "inline-block",
                marginTop: 16,
                padding: "10px 20px",
                background: "#14b8a6",
                color: "#0f1419",
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
