import AdminNav from "./AdminNav";

export const metadata = {
  title: "Callwen Admin",
};

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-gray-50">
      <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-gray-200 bg-white px-6">
        <div className="flex items-center gap-6">
          <span className="text-sm font-semibold text-gray-900">
            Callwen Admin
          </span>
          <AdminNav />
        </div>
      </header>
      <main>{children}</main>
    </div>
  );
}
