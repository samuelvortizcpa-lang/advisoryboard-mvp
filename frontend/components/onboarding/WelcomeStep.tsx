"use client";

interface Props {
  onNext: () => void;
}

export default function WelcomeStep({ onNext }: Props) {
  return (
    <div className="w-full max-w-lg text-center">
      {/* Sparkles icon */}
      <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-amber-50">
        <svg
          className="h-8 w-8 text-amber-500"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.5}
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z" />
          <path d="M20 3v4" />
          <path d="M22 5h-4" />
          <path d="M4 17v2" />
          <path d="M5 18H3" />
        </svg>
      </div>

      <h1
        className="text-3xl font-semibold text-gray-900"
        style={{ fontFamily: "'Cormorant Garamond', Georgia, serif" }}
      >
        Welcome to Callwen
      </h1>
      <p className="mt-2 text-lg text-gray-500">
        Let&apos;s get you set up in under 2 minutes.
      </p>

      {/* Value cards */}
      <div className="mt-8 space-y-3 text-left">
        <ValueCard
          icon={<UploadIcon />}
          title="Upload client documents"
          subtitle="Tax returns, engagement letters, financials — we handle it all."
        />
        <ValueCard
          icon={<MessageIcon />}
          title="Ask questions, get cited answers"
          subtitle="AI-powered answers with source citations and confidence scores."
        />
        <ValueCard
          icon={<ShieldIcon />}
          title="Stay IRC §7216 compliant"
          subtitle="Built-in consent tracking for tax preparers."
        />
      </div>

      <button
        onClick={onNext}
        className="mt-8 w-full rounded-lg bg-gray-900 py-3 text-sm font-medium text-white transition hover:bg-gray-800"
      >
        Let&apos;s get started &rarr;
      </button>
      <p className="mt-3 text-xs text-gray-400">
        You can always explore on your own
      </p>
    </div>
  );
}

function ValueCard({
  icon,
  title,
  subtitle,
}: {
  icon: React.ReactNode;
  title: string;
  subtitle: string;
}) {
  return (
    <div className="flex items-start gap-3 rounded-lg bg-gray-50 p-4">
      <div className="mt-0.5 shrink-0 text-gray-400">{icon}</div>
      <div>
        <p className="text-sm font-medium text-gray-900">{title}</p>
        <p className="text-xs text-gray-500">{subtitle}</p>
      </div>
    </div>
  );
}

function UploadIcon() {
  return (
    <svg
      className="h-5 w-5"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="17 8 12 3 7 8" />
      <line x1="12" y1="3" x2="12" y2="15" />
    </svg>
  );
}

function MessageIcon() {
  return (
    <svg
      className="h-5 w-5"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  );
}

function ShieldIcon() {
  return (
    <svg
      className="h-5 w-5"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  );
}
