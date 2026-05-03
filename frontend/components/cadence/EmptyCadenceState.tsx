"use client";

interface EmptyCadenceStateProps {
  isAdmin: boolean;
  onPickClick: () => void;
}

export default function EmptyCadenceState({ isAdmin, onPickClick }: EmptyCadenceStateProps) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-8 text-center shadow-sm">
      <svg
        className="mx-auto h-10 w-10 text-gray-300"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={1.5}
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5"
        />
      </svg>
      <p className="mt-3 text-sm text-gray-500">
        No cadence assigned. Pick a template to get started.
      </p>
      <div className="relative mt-4 inline-block">
        <button
          onClick={onPickClick}
          disabled={!isAdmin}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Pick template
        </button>
        {!isAdmin && (
          <p className="mt-1 text-xs text-gray-400">Admin only</p>
        )}
      </div>
    </div>
  );
}
