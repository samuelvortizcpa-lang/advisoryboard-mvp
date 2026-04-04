"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

interface CoverageRingProps {
  reviewed: number | null;
  total: number | null;
  href?: string;
}

const RADIUS = 44;
const STROKE = 7;
const SIZE = 104;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

export default function CoverageRing({ reviewed, total, href }: CoverageRingProps) {
  const [mounted, setMounted] = useState(false);
  const ringRef = useRef<SVGCircleElement>(null);

  const loading = reviewed === null || total === null;
  const pct = !loading && total > 0 ? Math.round((reviewed / total) * 100) : 0;
  const offset = CIRCUMFERENCE - (CIRCUMFERENCE * (loading ? 0 : pct)) / 100;

  // Ring color based on coverage
  const ringColor = pct >= 75 ? "#22c55e" : pct < 25 ? "#f59e0b" : "#3b82f6";

  useEffect(() => {
    // Small delay so the initial render has full offset, then animate
    const id = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(id);
  }, []);

  const card = (
    <div className={`group relative flex flex-col items-center justify-center rounded-xl border border-gray-100 bg-white p-4 shadow-sm transition-all duration-150${href ? " cursor-pointer hover:-translate-y-0.5 hover:shadow-md" : ""}`}>
      {href && (
        <svg
          className="absolute right-3 top-3 h-4 w-4 text-gray-300 opacity-0 transition-opacity duration-150 group-hover:opacity-100"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <polyline points="9 18 15 12 9 6" />
        </svg>
      )}

      {/* Ring */}
      <svg width={SIZE} height={SIZE} className="block">
        {/* Track */}
        <circle
          cx={SIZE / 2}
          cy={SIZE / 2}
          r={RADIUS}
          fill="none"
          stroke="currentColor"
          strokeWidth={STROKE}
          className="text-gray-200 dark:text-gray-700"
        />
        {/* Progress arc */}
        {loading ? (
          <circle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={RADIUS}
            fill="none"
            stroke="currentColor"
            strokeWidth={STROKE}
            strokeDasharray={CIRCUMFERENCE}
            strokeDashoffset={CIRCUMFERENCE * 0.75}
            strokeLinecap="round"
            className="origin-center animate-spin text-gray-300"
            style={{ transformOrigin: `${SIZE / 2}px ${SIZE / 2}px`, animationDuration: "1.2s" }}
          />
        ) : (
          <circle
            ref={ringRef}
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={RADIUS}
            fill="none"
            stroke={ringColor}
            strokeWidth={STROKE}
            strokeDasharray={CIRCUMFERENCE}
            strokeDashoffset={mounted ? offset : CIRCUMFERENCE}
            strokeLinecap="round"
            style={{
              transition: mounted ? "stroke-dashoffset 800ms ease-out" : "none",
              transform: "rotate(-90deg)",
              transformOrigin: `${SIZE / 2}px ${SIZE / 2}px`,
            }}
          />
        )}
        {/* Center text */}
        {!loading && (
          <text
            x={SIZE / 2}
            y={SIZE / 2}
            textAnchor="middle"
            dominantBaseline="central"
            className="fill-gray-900 text-2xl font-semibold dark:fill-gray-100"
            style={{ fontSize: 24, fontWeight: 600 }}
          >
            {pct}%
          </text>
        )}
      </svg>

      {/* Labels below ring */}
      <p className="mt-2 text-xs text-gray-500">Strategies reviewed</p>
      <p className="mt-0.5 text-[11px] text-gray-400">
        {loading ? "\u00A0" : `${reviewed} of ${total} clients`}
      </p>
    </div>
  );

  if (href) {
    return <Link href={href} className="block">{card}</Link>;
  }

  return card;
}
