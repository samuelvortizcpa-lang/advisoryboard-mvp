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
    </main>
  );
}
