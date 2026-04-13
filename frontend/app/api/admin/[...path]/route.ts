// AUTH INVARIANT: this catch-all proxy is the single entry point for all
// /api/admin/* traffic. Authentication and authorization are enforced here,
// NOT in middleware. Do NOT add sibling routes under /api/admin/ without
// either (a) adding them to middleware gating, or (b) replicating the
// auth() + ADMIN_USER_IDS check at the top of the new handler.

/**
 * Server-side admin API proxy.
 *
 * Forwards requests to the Railway backend's /api/admin/* endpoints with
 * the caller's Clerk JWT attached. The backend's `verify_admin_access()`
 * validates the JWT and checks the user against ADMIN_USER_ID.
 *
 * Auth flow:
 *   1. Clerk middleware has already verified the session cookie.
 *   2. This route handler calls auth() to get the userId and getToken().
 *   3. We reject early if the user is not authenticated or not in
 *      ADMIN_USER_IDS (defense-in-depth — the backend also checks).
 *   4. We obtain a fresh Clerk session JWT via getToken().
 *   5. We forward the request to the backend with Authorization: Bearer <jwt>.
 *   6. The backend's verify_admin_access() validates the JWT and checks
 *      whether sub matches ADMIN_USER_ID.
 */

import { auth } from "@clerk/nextjs/server";
import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL =
  process.env.BACKEND_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://localhost:8000";

function getAdminUserIds(): Set<string> {
  const raw = process.env.ADMIN_USER_IDS ?? "";
  return new Set(
    raw
      .split(",")
      .map((id) => id.trim())
      .filter(Boolean),
  );
}

async function handleProxy(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
): Promise<NextResponse> {
  // 1. Authenticate via Clerk
  const { userId, getToken } = await auth();

  if (!userId) {
    return NextResponse.json(
      { detail: "Authentication required" },
      { status: 401 },
    );
  }

  // 2. Check admin allowlist (defense-in-depth — backend also checks)
  const adminIds = getAdminUserIds();
  // Fail-closed: empty/missing ADMIN_USER_IDS means the Set is empty,
  // which means no user ID can match, which means everyone is denied.
  // Do NOT add a "size > 0" guard here — that would re-introduce fail-open.
  if (!adminIds.has(userId)) {
    if (adminIds.size === 0) {
      console.warn("ADMIN_USER_IDS is not configured; denying admin access. Set ADMIN_USER_IDS in the deployment environment.");
    }
    return NextResponse.json(
      { detail: "Admin access required" },
      { status: 403 },
    );
  }

  // 3. Get a fresh Clerk session JWT to forward to the backend
  const clerkToken = await getToken();
  if (!clerkToken) {
    return NextResponse.json(
      { detail: "Unable to obtain session token" },
      { status: 401 },
    );
  }

  // 4. Build the forwarded request URL
  const { path } = await params;
  const backendPath = `/api/admin/${path.join("/")}`;
  const url = new URL(backendPath, BACKEND_URL);
  // Forward query string
  req.nextUrl.searchParams.forEach((value, key) => {
    url.searchParams.append(key, value);
  });

  // 5. Forward the request
  const headers: Record<string, string> = {
    Authorization: `Bearer ${clerkToken}`,
  };

  // Forward Content-Type for requests with a body
  const contentType = req.headers.get("content-type");
  if (contentType) {
    headers["Content-Type"] = contentType;
  }

  const hasBody = req.method !== "GET" && req.method !== "HEAD";

  try {
    const backendRes = await fetch(url.toString(), {
      method: req.method,
      headers,
      body: hasBody ? await req.text() : undefined,
    });

    // 6. Return the backend's response transparently
    const responseHeaders = new Headers();
    const ct = backendRes.headers.get("content-type");
    if (ct) responseHeaders.set("content-type", ct);
    const cd = backendRes.headers.get("content-disposition");
    if (cd) responseHeaders.set("content-disposition", cd);

    return new NextResponse(backendRes.body, {
      status: backendRes.status,
      statusText: backendRes.statusText,
      headers: responseHeaders,
    });
  } catch (err) {
    console.error("[admin-proxy] Backend request failed:", err);
    return NextResponse.json(
      { detail: "Backend unavailable" },
      { status: 502 },
    );
  }
}

export const GET = handleProxy;
export const POST = handleProxy;
export const PATCH = handleProxy;
export const DELETE = handleProxy;
export const PUT = handleProxy;
