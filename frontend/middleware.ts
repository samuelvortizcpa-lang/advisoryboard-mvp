import { clerkMiddleware } from "@clerk/nextjs/server";
import { NextRequest, NextResponse, NextFetchEvent } from "next/server";

const CLERK_FAPI = "https://clerk.callwen.com";
const PROXY_URL = "https://callwen.com/__clerk";

const clerkHandler = clerkMiddleware();

export default async function middleware(req: NextRequest, event: NextFetchEvent) {
  // Public pages — skip Clerk auth entirely
  if (
    req.nextUrl.pathname.startsWith("/consent/sign") ||
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
