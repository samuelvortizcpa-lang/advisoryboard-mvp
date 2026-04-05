"use client";

import { useAuth } from "@clerk/nextjs";
import { useState } from "react";

import { createOnboardingApi } from "@/lib/api";

import WelcomeStep from "./WelcomeStep";

interface Props {
  onComplete: () => void;
}

const STEP_LABELS = ["Welcome", "Add client", "Upload", "Ask AI", "Done"];

export default function OnboardingWizard({ onComplete }: Props) {
  const { getToken } = useAuth();
  const [currentStep, setCurrentStep] = useState(0);
  const [createdClientId, setCreatedClientId] = useState<string | null>(null);
  const [createdClientName, setCreatedClientName] = useState<string | null>(null);
  const [uploadedDocumentId, setUploadedDocumentId] = useState<string | null>(null);
  const [skipping, setSkipping] = useState(false);

  function nextStep() {
    setCurrentStep((s) => Math.min(s + 1, STEP_LABELS.length - 1));
  }

  async function handleSkip() {
    setSkipping(true);
    try {
      await createOnboardingApi(getToken).complete();
    } catch {
      // non-fatal — still dismiss the wizard
    }
    onComplete();
  }

  function renderStep() {
    switch (currentStep) {
      case 0:
        return <WelcomeStep onNext={nextStep} />;
      case 1:
        // AddClientStep — placeholder for next PR
        return (
          <StepPlaceholder
            title="Add your first client"
            onNext={() => {
              setCreatedClientId(null);
              setCreatedClientName(null);
              nextStep();
            }}
          />
        );
      case 2:
        // UploadDocStep — placeholder for next PR
        return (
          <StepPlaceholder
            title={`Upload a document${createdClientName ? ` for ${createdClientName}` : ""}`}
            onNext={() => {
              setUploadedDocumentId(null);
              nextStep();
            }}
          />
        );
      case 3:
        // AskAIStep — placeholder for next PR
        return <StepPlaceholder title="Ask AI a question" onNext={nextStep} />;
      case 4:
        // FinishStep — placeholder for next PR
        return (
          <div className="text-center">
            <p className="text-2xl font-semibold text-gray-900">
              You&apos;re all set!
            </p>
            <button
              onClick={async () => {
                try {
                  await createOnboardingApi(getToken).complete();
                } catch {
                  // non-fatal
                }
                onComplete();
              }}
              className="mt-6 rounded-lg bg-gray-900 px-8 py-3 text-sm font-medium text-white transition hover:bg-gray-800"
            >
              Go to dashboard
            </button>
          </div>
        );
      default:
        return null;
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-white">
      {/* Top bar */}
      <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4">
        {/* Logo */}
        <span
          className="text-lg font-bold tracking-wide text-gray-900"
          style={{ fontFamily: "'Cormorant Garamond', Georgia, serif" }}
        >
          Callwen
        </span>

        {/* Step indicator */}
        <div className="hidden sm:flex items-center gap-0">
          {STEP_LABELS.map((label, i) => (
            <div key={label} className="flex items-center">
              {i > 0 && (
                <div
                  className={`h-px w-8 ${
                    i <= currentStep ? "bg-gray-900" : "bg-gray-200"
                  }`}
                />
              )}
              <div className="flex flex-col items-center gap-1">
                <div
                  className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-medium transition-colors ${
                    i < currentStep
                      ? "bg-green-500 text-white"
                      : i === currentStep
                        ? "bg-gray-900 text-white"
                        : "border-2 border-gray-300 text-gray-400"
                  }`}
                >
                  {i < currentStep ? (
                    <svg
                      className="h-3 w-3"
                      viewBox="0 0 12 12"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth={2.5}
                    >
                      <path d="M2 6l3 3 5-5" />
                    </svg>
                  ) : (
                    i + 1
                  )}
                </div>
                <span
                  className={`text-[10px] ${
                    i <= currentStep
                      ? "font-medium text-gray-700"
                      : "text-gray-400"
                  }`}
                >
                  {label}
                </span>
              </div>
            </div>
          ))}
        </div>

        {/* Skip button */}
        <button
          onClick={handleSkip}
          disabled={skipping}
          className="text-sm text-gray-400 transition-colors hover:text-gray-600 disabled:opacity-50"
        >
          {skipping ? "Skipping…" : "Skip setup"}
        </button>
      </div>

      {/* Content area */}
      <div className="flex flex-1 items-center justify-center px-6">
        {renderStep()}
      </div>
    </div>
  );
}

/** Temporary placeholder for steps not yet implemented. */
function StepPlaceholder({
  title,
  onNext,
}: {
  title: string;
  onNext: () => void;
}) {
  return (
    <div className="text-center">
      <p className="text-xl font-semibold text-gray-900">{title}</p>
      <p className="mt-2 text-sm text-gray-400">Coming soon</p>
      <button
        onClick={onNext}
        className="mt-6 rounded-lg bg-gray-900 px-8 py-3 text-sm font-medium text-white transition hover:bg-gray-800"
      >
        Continue &rarr;
      </button>
    </div>
  );
}
