"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useState } from "react";

import { createClientsApi } from "@/lib/api";

interface Props {
  onNext: () => void;
  onSkip: () => void;
  onClientCreated: (clientId: string, clientName: string) => void;
}

const ENTITY_TYPES = ["Individual", "Business", "Trust", "Estate", "Non-profit"];

export default function AddClientStep({ onNext, onSkip, onClientCreated }: Props) {
  const { getToken } = useAuth();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [entityType, setEntityType] = useState("Individual");
  const [industry, setIndustry] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [limitError, setLimitError] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;

    setSubmitting(true);
    setError(null);
    setLimitError(false);

    try {
      const api = createClientsApi(getToken);
      const client = await api.create({
        name: name.trim(),
        email: email.trim() || undefined,
        entity_type: entityType,
        industry: industry.trim() || undefined,
      });
      onClientCreated(client.id, client.name);
      onNext();
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : "Something went wrong. Please try again.";
      if (msg.includes("403") || msg.toLowerCase().includes("limit")) {
        setLimitError(true);
        setError("Client limit reached.");
      } else {
        setError(msg);
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="w-full max-w-md">
      <p className="text-xs font-medium uppercase tracking-widest text-gray-400">
        Step 1 of 3
      </p>
      <h2 className="mt-2 text-2xl font-semibold text-gray-900">
        Add your first client
      </h2>
      <p className="mt-1 text-sm text-gray-500">
        This takes about 30 seconds. You can always add more later.
      </p>

      <form onSubmit={handleSubmit} className="mt-6 space-y-4">
        {/* Client name */}
        <div>
          <label htmlFor="ob-name" className="mb-1 block text-sm font-medium text-gray-700">
            Full name or business name
          </label>
          <input
            id="ob-name"
            type="text"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g., Smith & Associates LLC"
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-transparent focus:ring-2 focus:ring-gray-900"
          />
        </div>

        {/* Email */}
        <div>
          <label htmlFor="ob-email" className="mb-1 block text-sm font-medium text-gray-700">
            Client email
            <span className="ml-1 font-normal text-gray-400">(optional)</span>
          </label>
          <input
            id="ob-email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="e.g., john@smithcpa.com"
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-transparent focus:ring-2 focus:ring-gray-900"
          />
        </div>

        {/* Entity type */}
        <div>
          <label htmlFor="ob-entity" className="mb-1 block text-sm font-medium text-gray-700">
            Entity type
            <span className="ml-1 font-normal text-gray-400">(optional)</span>
          </label>
          <select
            id="ob-entity"
            value={entityType}
            onChange={(e) => setEntityType(e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-transparent focus:ring-2 focus:ring-gray-900"
          >
            {ENTITY_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>

        {/* Industry */}
        <div>
          <label htmlFor="ob-industry" className="mb-1 block text-sm font-medium text-gray-700">
            Industry
            <span className="ml-1 font-normal text-gray-400">(optional)</span>
          </label>
          <input
            id="ob-industry"
            type="text"
            value={industry}
            onChange={(e) => setIndustry(e.target.value)}
            placeholder="e.g., Real estate, Healthcare"
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-transparent focus:ring-2 focus:ring-gray-900"
          />
        </div>

        {/* Error */}
        {error && (
          <div className="text-sm text-red-600">
            {error}
            {limitError && (
              <>
                {" "}
                <Link
                  href="/dashboard/settings/subscriptions"
                  className="font-medium underline hover:text-red-700"
                >
                  Upgrade your plan to add more.
                </Link>
              </>
            )}
          </div>
        )}

        {/* Submit */}
        <button
          type="submit"
          disabled={submitting || !name.trim()}
          className="mt-6 flex w-full items-center justify-center gap-2 rounded-lg bg-gray-900 py-3 text-sm font-medium text-white transition hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting && <Spinner />}
          {submitting ? "Creating…" : "Add client & continue \u2192"}
        </button>
      </form>

      {/* Skip */}
      <button
        onClick={onSkip}
        disabled={submitting}
        className="mt-2 w-full py-2 text-sm text-gray-500 transition-colors hover:text-gray-700 disabled:opacity-50"
      >
        Skip — I&apos;ll add clients later
      </button>
    </div>
  );
}

function Spinner() {
  return (
    <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
  );
}
