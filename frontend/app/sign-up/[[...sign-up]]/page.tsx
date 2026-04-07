import type { Metadata } from "next";
import { SignUp } from "@clerk/nextjs";
import AuthLayout, { clerkAppearance } from "@/components/auth/AuthLayout";

export const metadata: Metadata = {
  title: "Get started — Callwen",
  description: "Create your free Callwen account. AI-powered document intelligence for CPAs — no credit card required.",
};

export default function SignUpPage() {
  return (
    <AuthLayout mode="sign-up">
      <SignUp
        appearance={clerkAppearance}
        path="/sign-up"
        signInUrl="/sign-in"
        fallbackRedirectUrl="/dashboard"
      />
    </AuthLayout>
  );
}
