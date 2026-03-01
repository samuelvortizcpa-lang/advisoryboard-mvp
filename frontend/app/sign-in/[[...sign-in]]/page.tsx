import { SignIn } from "@clerk/nextjs";

export default function SignInPage() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center bg-gray-50">
      <div className="mb-8 text-center">
        <h1 className="text-3xl font-semibold tracking-tight text-gray-900">
          AdvisoryBoard
        </h1>
        <p className="mt-2 text-sm text-gray-500">
          Sign in to access your advisory board
        </p>
      </div>

      <SignIn
        path="/sign-in"
        signUpUrl="/sign-up"
        fallbackRedirectUrl="/dashboard"
      />
    </main>
  );
}
