export interface MemberRowProps {
  name: string;
  email?: string;
  role?: string;
  stats?: { clients: number; queries: number };
  lastActive?: string;
  avatarColor?: string;
}

function getInitials(name: string): string {
  const parts = name.trim().split(/\s+/);
  const first = parts[0]?.[0]?.toUpperCase() ?? "";
  const last = parts.length > 1 ? parts[parts.length - 1][0]?.toUpperCase() ?? "" : "";
  return first + last || "U";
}

const roleBadge: Record<string, string> = {
  admin: "bg-purple-100 text-purple-700",
  member: "bg-gray-100 text-gray-700",
};

export default function MemberRow({ name, email, role, stats, lastActive }: MemberRowProps) {
  return (
    <div className="flex items-center gap-3 border-b border-gray-100 py-3 last:border-b-0">
      {/* Avatar */}
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-100 text-xs font-semibold text-blue-700">
        {getInitials(name)}
      </div>

      {/* Name + email */}
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-gray-900">{name}</p>
        {email && <p className="truncate text-xs text-gray-500">{email}</p>}
      </div>

      {/* Role badge */}
      {role && (
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-medium ${roleBadge[role.toLowerCase()] ?? roleBadge.member}`}
        >
          {role}
        </span>
      )}

      {/* Stats */}
      {stats && (
        <div className="hidden gap-4 text-xs text-gray-500 sm:flex">
          <span>{stats.clients} clients</span>
          <span>{stats.queries} queries</span>
        </div>
      )}

      {/* Last active */}
      {lastActive && (
        <span className="shrink-0 text-xs text-gray-400">{lastActive}</span>
      )}
    </div>
  );
}
