"use client";

import { useAuth } from "@clerk/nextjs";
import { useState } from "react";

import { createOnboardingApi } from "@/lib/api";

import AddClientStep from "./AddClientStep";
import AskAIStep from "./AskAIStep";
import FinishStep from "./FinishStep";
import UploadDocStep from "./UploadDocStep";
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

  async function handleFinish() {
    try {
      await createOnboardingApi(getToken).complete();
    } catch {
      // non-fatal
    }
    onComplete();
  }

  function renderStep() {
    switch (currentStep) {
      case 0:
        return <WelcomeStep onNext={nextStep} />;
      case 1:
        return (
          <AddClientStep
            onNext={nextStep}
            onSkip={nextStep}
            onClientCreated={(id, name) => {
              setCreatedClientId(id);
              setCreatedClientName(name);
            }}
          />
        );
      case 2:
        return (
          <UploadDocStep
            onNext={nextStep}
            onSkip={nextStep}
            clientId={createdClientId}
            clientName={createdClientName}
            onDocUploaded={(id) => setUploadedDocumentId(id)}
          />
        );
      case 3:
        return (
          <AskAIStep
            onNext={nextStep}
            onSkip={nextStep}
            clientId={createdClientId}
            clientName={createdClientName}
            documentId={uploadedDocumentId}
          />
        );
      case 4:
        return (
          <FinishStep
            onComplete={handleFinish}
            clientId={createdClientId}
            clientName={createdClientName}
          />
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
        <div className="hidden items-center gap-0 sm:flex">
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
                {i < currentStep ? (
                  <button
                    onClick={() => setCurrentStep(i)}
                    className="flex h-6 w-6 items-center justify-center rounded-full bg-green-500 text-white transition-colors hover:bg-green-600"
                    title={`Go back to ${label}`}
                  >
                    <svg
                      className="h-3 w-3"
                      viewBox="0 0 12 12"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth={2.5}
                    >
                      <path d="M2 6l3 3 5-5" />
                    </svg>
                  </button>
                ) : (
                  <div
                    className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-medium transition-colors ${
                      i === currentStep
                        ? "bg-gray-900 text-white"
                        : "border-2 border-gray-300 text-gray-400"
                    }`}
                  >
                    {i + 1}
                  </div>
                )}
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
          {skipping ? "Skipping\u2026" : "Skip setup"}
        </button>
      </div>

      {/* Content area */}
      <div className="flex flex-1 items-center justify-center px-6">
        {renderStep()}
      </div>
    </div>
  );
}
