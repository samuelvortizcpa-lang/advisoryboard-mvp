"use client";

import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Unhandled error:", error);
  }, [error]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="max-w-md w-full text-center px-6">
        <h1 className="text-6xl font-bold text-gray-900 mb-4">Oops</h1>
        <p className="text-lg text-gray-600 mb-8">
          Something went wrong. Please try again.
        </p>
        <button
          onClick={reset}
          className="inline-flex items-center px-6 py-3 bg-gray-900 text-white rounded-lg hover:bg-gray-800 transition-colors"
        >
          Try again
        </button>
      </div>
    </div>
  );
}
