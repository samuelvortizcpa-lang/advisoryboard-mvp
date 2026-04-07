import type { Metadata } from "next";
import { SignIn } from "@clerk/nextjs";
import AuthLayout, { clerkAppearance } from "@/components/auth/AuthLayout";

export const metadata: Metadata = {
  title: "Sign in — Callwen",
  description: "Sign in to your Callwen dashboard.",
};

export default async function SignInPage({
  searchParams,
}: {
  searchParams: Promise<{ redirect_url?: string }>;
}) {
  const params = await searchParams;
  const redirectUrl = params.redirect_url || "/dashboard";

  return (
    <AuthLayout mode="sign-in">
      <SignIn
        appearance={clerkAppearance}
        path="/sign-in"
        signUpUrl="/sign-up"
        fallbackRedirectUrl={redirectUrl}
      />
    </AuthLayout>
  );
}
