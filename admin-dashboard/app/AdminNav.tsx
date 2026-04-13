"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Platform Dashboard" },
  { href: "/rag-analytics", label: "RAG Analytics" },
];

export default function AdminNav() {
  const pathname = usePathname();

  return (
    <nav className="flex items-center gap-4">
      {LINKS.map(({ href, label }) => {
        const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            className={`text-xs font-medium transition-colors ${
              active
                ? "text-blue-600"
                : "text-gray-400 hover:text-gray-600"
            }`}
          >
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
