import { clerkMiddleware } from "@clerk/nextjs/server";
import { NextRequest, NextResponse, NextFetchEvent } from "next/server";

const CLERK_FAPI = "https://clerk.callwen.com";
const PROXY_URL = "https://callwen.com/__clerk";

function getAdminUserIds(): Set<string> {
  const raw = process.env.ADMIN_USER_IDS ?? "";
  return new Set(
    raw
      .split(",")
      .map((id) => id.trim())
      .filter(Boolean),
  );
}

// clerkMiddleware with a handler — the handler runs after Clerk has
// authenticated the request, giving us access to auth() for route-specific
// checks like the admin gate.
const clerkHandler = clerkMiddleware(async (auth, request) => {
  const isAdminPage = request.nextUrl.pathname.startsWith("/admin");
  // /api/admin/* is handled by the Route Handler's own auth() call,
  // so we only gate page routes here.
  if (!isAdminPage) {
    return NextResponse.next();
  }

  // Admin page route — require authentication + admin allowlist
  const { userId, redirectToSignIn } = await auth();

  if (!userId) {
    return redirectToSignIn({ returnBackUrl: request.url });
  }

  const adminIds = getAdminUserIds();
  // TODO: Replace ADMIN_USER_IDS env var check with Clerk organization
  // roles or user metadata once role-based access is set up.
  if (adminIds.size > 0 && !adminIds.has(userId)) {
    // Non-admin authenticated user — redirect to home
    return NextResponse.redirect(new URL("/", request.url));
  }

  return NextResponse.next();
});

export default async function middleware(req: NextRequest, event: NextFetchEvent) {
  // Public pages — skip Clerk auth entirely
  if (
    req.nextUrl.pathname.startsWith("/consent/sign") ||
    req.nextUrl.pathname.startsWith("/checkin/") ||
    req.nextUrl.pathname.startsWith("/extension-auth-callback") ||
    req.nextUrl.pathname === "/privacy" ||
    req.nextUrl.pathname === "/terms"
  ) {
    return NextResponse.next();
  }

  if (req.nextUrl.pathname.startsWith("/__clerk")) {
    const clerkPath = req.nextUrl.pathname.replace("/__clerk", "") + req.nextUrl.search;
    const target = `${CLERK_FAPI}${clerkPath}`;

    const headers = new Headers(req.headers);
    headers.set("Clerk-Proxy-Url", PROXY_URL);
    headers.set("Clerk-Secret-Key", process.env.CLERK_SECRET_KEY || "");
    headers.set("Host", new URL(CLERK_FAPI).host);
    headers.delete("connection");

    const res = await fetch(target, {
      method: req.method,
      headers,
      body: req.method !== "GET" && req.method !== "HEAD" ? req.body : undefined,
      redirect: "manual",
    });

    const responseHeaders = new Headers(res.headers);
    responseHeaders.delete("content-encoding");

    return new NextResponse(res.body, {
      status: res.status,
      statusText: res.statusText,
      headers: responseHeaders,
    });
  }

  return clerkHandler(req, event);
}

export const config = {
  matcher: [
    '/__clerk/(.*)',
    '/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)',
    '/(api|trpc)(.*)',
  ],
};
