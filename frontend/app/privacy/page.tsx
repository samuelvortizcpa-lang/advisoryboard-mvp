import Link from "next/link";

export const metadata = {
  title: "Privacy Policy — Callwen",
  description: "Callwen privacy policy for AI-powered document intelligence.",
};

export default function PrivacyPolicyPage() {
  return (
    <main className="min-h-screen bg-white">
      <div className="mx-auto max-w-3xl px-6 py-16 sm:py-24">
        <h1 className="text-3xl font-bold tracking-tight text-gray-900">
          Privacy Policy
        </h1>
        <p className="mt-2 text-sm text-gray-500">
          Last Updated: April 2, 2026
        </p>

        <div className="mt-10 space-y-10 text-[15px] leading-relaxed text-gray-700">
          {/* 1 */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900">
              1. Introduction
            </h2>
            <p className="mt-3">
              Callwen, Inc. (&quot;Callwen,&quot; &quot;we,&quot;
              &quot;our,&quot; or &quot;us&quot;) provides an AI-powered
              document intelligence platform for financial professionals at{" "}
              <a
                href="https://callwen.com"
                className="text-blue-600 hover:underline"
              >
                callwen.com
              </a>
              . Our founder is a licensed CPA, and we built Callwen with
              professional standards of care in mind.
            </p>
            <p className="mt-3">
              This Privacy Policy describes how we collect, use, store, and
              protect your information when you use our platform. By using
              Callwen, you agree to the practices described in this policy.
            </p>
          </section>

          {/* 2 */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900">
              2. Information We Collect
            </h2>

            <h3 className="mt-4 font-medium text-gray-900">
              Account Information
            </h3>
            <p className="mt-2">
              When you create an account, we collect your name, email address,
              and authentication credentials through Clerk (including Google
              sign-in). If you join or create an organization, we also collect
              organization name and role details.
            </p>

            <h3 className="mt-4 font-medium text-gray-900">
              Client and Document Data
            </h3>
            <p className="mt-2">
              You may upload documents, create client records, and generate
              AI-powered content (briefs, action items, chat responses). We
              store these to provide our service.
            </p>

            <h3 className="mt-4 font-medium text-gray-900">Usage Data</h3>
            <p className="mt-2">
              We collect query counts, feature usage, login timestamps, browser
              type, and IP address to operate and improve the service.
            </p>

            <h3 className="mt-4 font-medium text-gray-900">
              Browser Extension Data
            </h3>
            <p className="mt-2">
              The Callwen browser extension allows you to capture content from
              web pages directly into your Callwen workspace. The extension
              collects the following data only when you explicitly initiate a
              capture:
            </p>
            <ul className="mt-2 list-disc space-y-1.5 pl-5">
              <li>
                <strong>Captured content:</strong> text selections, full page
                text, screenshot images, and file URLs — transmitted only when
                you click the capture button
              </li>
              <li>
                <strong>Page metadata:</strong> URL and title of pages you
                capture from, used for source tracking and deduplication
              </li>
              <li>
                <strong>Auto-match signals:</strong> domain name and detected
                company names on the current page, sent to the server to suggest
                the correct client (paid plans only, only when auto-match is
                active)
              </li>
              <li>
                <strong>Parser-extracted data:</strong> when viewing Gmail,
                QuickBooks Online, or tax software, structured data is extracted
                (email fields, financial report data, form fields) — parsers
                activate only on paid plans, only on recognized platforms, and
                only when you initiate a capture
              </li>
              <li>
                <strong>Monitoring rule matches:</strong> if you configure
                monitoring rules, the extension checks page URLs and domains
                against your rules locally in the browser; only match
                notifications are generated, and page content is not transmitted
                unless you choose to capture
              </li>
            </ul>
            <p className="mt-3 font-medium text-gray-900">
              The extension does NOT collect:
            </p>
            <ul className="mt-2 list-disc space-y-1.5 pl-5">
              <li>
                Browsing history or page content from sites you visit without
                capturing
              </li>
              <li>
                Passwords, cookies, or authentication tokens from other websites
              </li>
              <li>
                Data from browser tabs other than the active tab during a
                capture
              </li>
              <li>Any data when the extension is not actively being used</li>
            </ul>
            <p className="mt-3">
              <strong>Local storage:</strong> the extension stores only your
              Callwen authentication token and a cache of client ID/name pairs
              in chrome.storage.local. No document content, email bodies, or
              client-sensitive data is persisted in the extension.
            </p>

            <h3 className="mt-4 font-medium text-gray-900">
              Payment Information
            </h3>
            <p className="mt-2">
              Payment processing is handled entirely by Stripe. We store only
              your Stripe customer ID and subscription status — we never see or
              store your credit card number.
            </p>
          </section>

          {/* 3 */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900">
              3. How We Use Your Information
            </h2>
            <ul className="mt-3 list-disc space-y-1.5 pl-5">
              <li>Provide, maintain, and improve the Callwen platform</li>
              <li>
                Process documents and queries through AI providers to deliver
                results
              </li>
              <li>Manage your account, organization, and subscription</li>
              <li>
                Communicate with you about service updates and account activity
              </li>
              <li>
                Analyze aggregate usage patterns to improve service reliability
              </li>
            </ul>
            <p className="mt-4 font-medium text-gray-900">
              We explicitly do NOT:
            </p>
            <ul className="mt-2 list-disc space-y-1.5 pl-5">
              <li>Sell your data to third parties</li>
              <li>Use your uploaded documents to train AI models</li>
              <li>
                Share data between organizations — each org&apos;s data is fully
                isolated
              </li>
              <li>Display advertisements or share data with ad networks</li>
            </ul>
          </section>

          {/* 4 */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900">
              4. Data Storage and Security
            </h2>
            <p className="mt-3">
              We use industry-leading infrastructure providers with strong
              security certifications:
            </p>
            <ul className="mt-3 list-disc space-y-1.5 pl-5">
              <li>
                <strong>Supabase</strong> (database and file storage) — SOC 2
                Type II certified
              </li>
              <li>
                <strong>Clerk</strong> (authentication) — SOC 2 Type II
                certified
              </li>
              <li>
                <strong>Vercel</strong> (frontend hosting) — SOC 2 Type II
                certified
              </li>
              <li>
                <strong>Stripe</strong> (payments) — PCI DSS Level 1 certified
              </li>
            </ul>
            <p className="mt-3">
              All data in transit is encrypted with TLS 1.2 or higher. Data at
              rest is encrypted with AES-256. Database connections use encrypted
              connection pooling. Access is controlled through role-based access
              control (RBAC) with Admin and Member roles.
            </p>
          </section>

          {/* 5 */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900">
              5. AI Processing
            </h2>
            <p className="mt-3">
              Callwen uses the following AI providers to process your documents
              and queries:
            </p>
            <ul className="mt-3 list-disc space-y-1.5 pl-5">
              <li>Anthropic (Claude)</li>
              <li>Google (Gemini)</li>
              <li>OpenAI (GPT)</li>
            </ul>
            <p className="mt-3">
              Under our API agreements with these providers, they do not retain
              your data or use it for model training. We send only the minimum
              data necessary to fulfill each request.
            </p>
          </section>

          {/* 6 */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900">
              6. Data Sharing
            </h2>
            <p className="mt-3">
              We share your information only with the following categories of
              recipients, and only as necessary to provide the service:
            </p>
            <ul className="mt-3 list-disc space-y-1.5 pl-5">
              <li>
                <strong>AI providers</strong> — Anthropic, Google, and OpenAI
                for document processing
              </li>
              <li>
                <strong>Infrastructure providers</strong> — Supabase, Vercel,
                Railway, and Clerk for hosting and authentication
              </li>
              <li>
                <strong>Stripe</strong> — for payment processing
              </li>
              <li>
                <strong>Legal requirements</strong> — when required by law,
                subpoena, or court order
              </li>
              <li>
                <strong>Business transfers</strong> — in connection with a
                merger, acquisition, or sale of assets (with notice to you)
              </li>
            </ul>
          </section>

          {/* 7 */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900">
              7. Data Retention
            </h2>
            <ul className="mt-3 list-disc space-y-1.5 pl-5">
              <li>
                <strong>Account data:</strong> retained while your account is
                active, plus 30 days after deletion
              </li>
              <li>
                <strong>Documents:</strong> retained while your account is
                active, plus 30 days after you delete them
              </li>
              <li>
                <strong>Usage logs:</strong> retained for 12 months
              </li>
              <li>
                <strong>Payment records:</strong> retained for 7 years for tax
                and legal compliance
              </li>
            </ul>
          </section>

          {/* 8 */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900">
              8. Your Rights
            </h2>
            <p className="mt-3">You have the right to:</p>
            <ul className="mt-2 list-disc space-y-1.5 pl-5">
              <li>
                <strong>Access</strong> your personal data
              </li>
              <li>
                <strong>Correct</strong> inaccurate information
              </li>
              <li>
                <strong>Delete</strong> your account and associated data
              </li>
              <li>
                <strong>Export</strong> your data in a portable format
              </li>
              <li>
                <strong>Restrict</strong> certain processing activities
              </li>
            </ul>
            <p className="mt-3">
              To exercise any of these rights, contact us at{" "}
              <a
                href="mailto:privacy@callwen.com"
                className="text-blue-600 hover:underline"
              >
                privacy@callwen.com
              </a>
              .
            </p>
          </section>

          {/* 9 */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900">
              9. Organization Data
            </h2>
            <p className="mt-3">
              If you use Callwen as part of an organization, the organization
              administrator controls access to the organization&apos;s data.
              Member access is scoped to the organization they belong to.
              When a member is removed from an organization, their access is
              revoked immediately. The organization owns its data — individual
              members do not retain access to organization data after removal.
            </p>
          </section>

          {/* 10 */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900">
              10. Cookies
            </h2>
            <p className="mt-3">
              Callwen uses only essential cookies required for authentication
              and session management. We do not use advertising cookies,
              tracking pixels, or third-party analytics cookies.
            </p>
          </section>

          {/* 11 */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900">
              11. Children&apos;s Privacy
            </h2>
            <p className="mt-3">
              Callwen is not intended for use by individuals under 18 years of
              age. We do not knowingly collect personal information from minors.
            </p>
          </section>

          {/* 12 */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900">
              12. California Privacy Rights (CCPA)
            </h2>
            <p className="mt-3">
              If you are a California resident, you have the right to know what
              personal information we collect, request deletion of your data,
              and opt out of data sales. We do not sell personal information.
              To exercise your rights, contact{" "}
              <a
                href="mailto:privacy@callwen.com"
                className="text-blue-600 hover:underline"
              >
                privacy@callwen.com
              </a>
              .
            </p>
          </section>

          {/* 13 */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900">
              13. Changes to This Policy
            </h2>
            <p className="mt-3">
              We may update this Privacy Policy from time to time. For material
              changes, we will provide at least 30 days&apos; notice via email
              or a prominent notice on our platform before the changes take
              effect.
            </p>
          </section>

          {/* 14 */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900">
              14. Contact Us
            </h2>
            <p className="mt-3">
              If you have questions about this Privacy Policy, contact us at:
            </p>
            <ul className="mt-2 space-y-1">
              <li>
                Email:{" "}
                <a
                  href="mailto:privacy@callwen.com"
                  className="text-blue-600 hover:underline"
                >
                  privacy@callwen.com
                </a>
              </li>
              <li>
                Web:{" "}
                <a
                  href="https://callwen.com"
                  className="text-blue-600 hover:underline"
                >
                  https://callwen.com
                </a>
              </li>
              <li>Callwen, Inc.</li>
              <li>Fort Lauderdale, Florida</li>
            </ul>
          </section>
        </div>

        {/* Back link */}
        <div className="mt-16 border-t border-gray-200 pt-8">
          <Link
            href="/"
            className="text-sm text-blue-600 hover:underline"
          >
            &larr; Back to Callwen
          </Link>
        </div>
      </div>
    </main>
  );
}
