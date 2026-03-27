import { SignIn } from "@clerk/nextjs";
import AuthLayout, { clerkAppearance } from "@/components/auth/AuthLayout";

export default function SignInPage() {
  return (
    <AuthLayout>
      <SignIn
        appearance={clerkAppearance}
        path="/sign-in"
        signUpUrl="/sign-up"
        fallbackRedirectUrl="/dashboard"
      />
    </AuthLayout>
  );
}
