"use client";

import { useCallback, useId, useRef, useState } from "react";

interface HelpTooltipProps {
  content: string;
  position?: "top" | "bottom" | "left" | "right";
  maxWidth?: number;
}

export default function HelpTooltip({
  content,
  position = "top",
  maxWidth = 240,
}: HelpTooltipProps) {
  const [visible, setVisible] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const tooltipId = useId();

  const show = useCallback(() => {
    timerRef.current = setTimeout(() => setVisible(true), 200);
  }, []);

  const hide = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    setVisible(false);
  }, []);

  const positionClasses: Record<string, string> = {
    top: "bottom-full left-1/2 -translate-x-1/2 mb-2",
    bottom: "top-full left-1/2 -translate-x-1/2 mt-2",
    left: "right-full top-1/2 -translate-y-1/2 mr-2",
    right: "left-full top-1/2 -translate-y-1/2 ml-2",
  };

  const arrowClasses: Record<string, string> = {
    top: "top-full left-1/2 -translate-x-1/2 border-t-gray-900 dark:border-t-gray-700 border-x-transparent border-b-transparent border-4",
    bottom: "bottom-full left-1/2 -translate-x-1/2 border-b-gray-900 dark:border-b-gray-700 border-x-transparent border-t-transparent border-4",
    left: "left-full top-1/2 -translate-y-1/2 border-l-gray-900 dark:border-l-gray-700 border-y-transparent border-r-transparent border-4",
    right: "right-full top-1/2 -translate-y-1/2 border-r-gray-900 dark:border-r-gray-700 border-y-transparent border-l-transparent border-4",
  };

  return (
    <span className="relative inline-flex items-center" onMouseEnter={show} onMouseLeave={hide}>
      <span
        aria-label="More info"
        aria-describedby={visible ? tooltipId : undefined}
        className="cursor-help text-gray-400 transition-colors hover:text-gray-600 dark:hover:text-gray-300"
      >
        <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
          <circle cx="12" cy="12" r="10" />
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 16v-4m0-4h.01" />
        </svg>
      </span>

      {visible && (
        <span
          id={tooltipId}
          role="tooltip"
          className={`absolute z-50 ${positionClasses[position]} pointer-events-none animate-in fade-in duration-150`}
          style={{ maxWidth }}
        >
          <span className="block rounded-md bg-gray-900 px-3 py-2 text-xs leading-relaxed text-white shadow-lg dark:bg-gray-700">
            {content}
          </span>
          <span className={`absolute ${arrowClasses[position]} h-0 w-0`} />
        </span>
      )}
    </span>
  );
}
