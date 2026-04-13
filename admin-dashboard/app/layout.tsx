import "./globals.css";
import AdminNav from "./AdminNav";

export const metadata = {
  title: "AdvisoryBoard Admin",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-50 antialiased">
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-gray-200 bg-white px-6">
          <div className="flex items-center gap-6">
            <span className="text-sm font-semibold text-gray-900">
              AdvisoryBoard Admin
            </span>
            <AdminNav />
          </div>
          <span className="text-xs text-gray-400">Local only</span>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
