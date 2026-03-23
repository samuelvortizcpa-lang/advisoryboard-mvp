import Link from "next/link";
import { SignUp } from "@clerk/nextjs";

export default function SignUpPage() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center bg-gray-50">
      <div className="mb-8 text-center">
        <h1 className="text-3xl font-semibold tracking-tight text-gray-900">
          Callwen
        </h1>
        <p className="mt-2 text-sm text-gray-500">
          Create an account to get started
        </p>
      </div>

      <SignUp
        path="/sign-up"
        signInUrl="/sign-in"
        fallbackRedirectUrl="/dashboard"
      />

      <p className="mt-6 max-w-sm text-center text-xs text-gray-400">
        By signing up, you agree to our{" "}
        <Link href="/terms" className="text-blue-600 hover:underline">Terms of Service</Link>
        {" "}and{" "}
        <Link href="/privacy" className="text-blue-600 hover:underline">Privacy Policy</Link>.
      </p>
    </main>
  );
}
