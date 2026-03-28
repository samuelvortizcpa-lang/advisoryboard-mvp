import type { Metadata } from "next";
import { SignUp } from "@clerk/nextjs";
import AuthLayout, { clerkAppearance } from "@/components/auth/AuthLayout";

export const metadata: Metadata = { title: "Create account" };

export default function SignUpPage() {
  return (
    <AuthLayout>
      <SignUp
        appearance={clerkAppearance}
        path="/sign-up"
        signInUrl="/sign-in"
        fallbackRedirectUrl="/dashboard"
      />
    </AuthLayout>
  );
}
