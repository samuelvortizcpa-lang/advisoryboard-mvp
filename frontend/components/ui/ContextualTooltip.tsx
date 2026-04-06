"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback, useEffect, useRef, useState } from "react";

import { createTooltipsApi } from "@/lib/api";

interface Props {
  tooltipId: string;
  targetRef: React.RefObject<HTMLElement | null>;
  title: string;
  description: string;
  position?: "top" | "bottom" | "left" | "right";
  dismissedTooltips: string[];
  onDismiss: (tooltipId: string) => void;
}

const AUTO_DISMISS_MS = 15_000;

export default function ContextualTooltip({
  tooltipId,
  targetRef,
  title,
  description,
  position = "bottom",
  dismissedTooltips,
  onDismiss,
}: Props) {
  const { getToken } = useAuth();
  const tooltipRef = useRef<HTMLDivElement>(null);
  const [coords, setCoords] = useState<{ top: number; left: number } | null>(null);
  const [visible, setVisible] = useState(false);
  const dismissed = useRef(false);

  const dismiss = useCallback(async () => {
    if (dismissed.current) return;
    dismissed.current = true;
    setVisible(false);
    onDismiss(tooltipId);
    try {
      await createTooltipsApi(getToken).dismiss(tooltipId);
    } catch {
      // non-fatal
    }
  }, [getToken, tooltipId, onDismiss]);

  // Position calculation
  useEffect(() => {
    if (dismissedTooltips.includes(tooltipId)) return;

    function update() {
      const el = targetRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const gap = 10;

      let top: number;
      let left: number;

      switch (position) {
        case "top":
          top = rect.top - gap;
          left = rect.left + rect.width / 2;
          break;
        case "left":
          top = rect.top + rect.height / 2;
          left = rect.left - gap;
          break;
        case "right":
          top = rect.top + rect.height / 2;
          left = rect.right + gap;
          break;
        case "bottom":
        default:
          top = rect.bottom + gap;
          left = rect.left + rect.width / 2;
          break;
      }

      setCoords({ top, left });
    }

    // Delay to let target render
    const t = setTimeout(() => {
      update();
      setVisible(true);
    }, 500);

    return () => clearTimeout(t);
  }, [targetRef, position, tooltipId, dismissedTooltips]);

  // Auto-dismiss
  useEffect(() => {
    if (!visible) return;
    const t = setTimeout(dismiss, AUTO_DISMISS_MS);
    return () => clearTimeout(t);
  }, [visible, dismiss]);

  if (dismissedTooltips.includes(tooltipId) || !coords) return null;

  const translateMap = {
    top: "-translate-x-1/2 -translate-y-full",
    bottom: "-translate-x-1/2",
    left: "-translate-x-full -translate-y-1/2",
    right: "-translate-y-1/2",
  };

  // Arrow styles per position
  const arrowMap = {
    top: "left-1/2 -translate-x-1/2 -bottom-1.5 border-l-transparent border-r-transparent border-b-transparent border-t-gray-900",
    bottom:
      "left-1/2 -translate-x-1/2 -top-1.5 border-l-transparent border-r-transparent border-t-transparent border-b-gray-900",
    left: "top-1/2 -translate-y-1/2 -right-1.5 border-t-transparent border-b-transparent border-r-transparent border-l-gray-900",
    right:
      "top-1/2 -translate-y-1/2 -left-1.5 border-t-transparent border-b-transparent border-l-transparent border-r-gray-900",
  };

  return (
    <div
      ref={tooltipRef}
      className={`fixed z-40 max-w-xs rounded-lg bg-gray-900 p-3 shadow-lg transition-opacity duration-300 ${
        visible ? "opacity-100" : "opacity-0"
      } ${translateMap[position]}`}
      style={{ top: coords.top, left: coords.left }}
    >
      {/* Arrow */}
      <div
        className={`absolute h-0 w-0 border-[6px] ${arrowMap[position]}`}
      />

      <p className="text-sm font-medium text-white">{title}</p>
      <p className="mt-1 text-xs text-gray-300">{description}</p>
      <button
        onClick={dismiss}
        className="mt-2 text-xs text-gray-400 transition-colors hover:text-white"
      >
        Got it
      </button>
    </div>
  );
}
