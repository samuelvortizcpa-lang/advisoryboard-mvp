import Link from "next/link";

export const metadata = {
  title: "Terms of Service — Callwen",
  description: "Callwen terms of service for AI-powered document intelligence.",
};

export default function TermsOfServicePage() {
  return (
    <main className="min-h-screen bg-white">
      <div className="mx-auto max-w-3xl px-6 py-16 sm:py-24">
        <h1 className="text-3xl font-bold tracking-tight text-gray-900">
          Terms of Service
        </h1>
        <p className="mt-2 text-sm text-gray-500">
          Last Updated: March 22, 2026
        </p>

        <div className="mt-10 space-y-10 text-[15px] leading-relaxed text-gray-700">
          {/* 1 */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900">
              1. Agreement to Terms
            </h2>
            <p className="mt-3">
              By accessing or using Callwen at{" "}
              <a
                href="https://callwen.com"
                className="text-blue-600 hover:underline"
              >
                callwen.com
              </a>{" "}
              (&quot;the Service&quot;), you agree to be bound by these Terms of
              Service (&quot;Terms&quot;). If you do not agree, do not use the
              Service. These Terms constitute a legal agreement between you and
              Callwen, Inc. (&quot;Callwen,&quot; &quot;we,&quot;
              &quot;our,&quot; or &quot;us&quot;).
            </p>
          </section>

          {/* 2 */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900">
              2. Description of Service
            </h2>
            <p className="mt-3">
              Callwen is an AI-powered document intelligence platform designed
              for financial professionals. The Service includes document upload
              and analysis, AI-powered question answering, client management,
              action item tracking, and related features.
            </p>
          </section>

          {/* 3 */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900">
              3. Accounts and Registration
            </h2>
            <p className="mt-3">
              You must provide accurate and complete information when creating
              an account. You are responsible for maintaining the security of
              your account credentials. Organization administrators are
              responsible for managing member access and permissions within
              their organization.
            </p>
            <p className="mt-3">
              We reserve the right to suspend or terminate accounts that violate
              these Terms, contain fraudulent information, or remain inactive
              for an extended period.
            </p>
          </section>

          {/* 4 */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900">
              4. Subscription and Payment
            </h2>
            <p className="mt-3">
              Callwen offers tiered subscription plans, including a free tier
              with limited usage. Paid subscriptions are billed through Stripe
              on a monthly or annual basis.
            </p>
            <ul className="mt-3 list-disc space-y-1.5 pl-5">
              <li>
                Subscriptions renew automatically unless cancelled before the
                end of the current billing period
              </li>
              <li>
                Cancellations take effect at the end of the current billing
                period — you retain access until then
              </li>
              <li>
                We do not provide pro-rated refunds for partial billing periods
              </li>
              <li>
                The Firm tier includes a base number of seats with the option to
                purchase add-on seats at an additional per-seat monthly fee
              </li>
              <li>
                We reserve the right to change pricing with 30 days&apos; notice
              </li>
            </ul>
          </section>

          {/* 5 */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900">
              5. Your Data
            </h2>
            <p className="mt-3">
              You retain ownership of all data you upload to or create within
              Callwen. By using the Service, you grant us a limited license to
              use your data solely for the purpose of providing and improving
              the Service.
            </p>
            <p className="mt-3">
              AI-generated content (briefs, summaries, action items, chat
              responses) is provided for informational purposes only. You are
              responsible for reviewing and verifying all AI-generated content
              before using it in professional deliverables.
            </p>
            <p className="mt-3">
              You may export your data at any time through the platform&apos;s
              export features.
            </p>
          </section>

          {/* 6 */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900">
              6. Acceptable Use
            </h2>
            <p className="mt-3">You agree not to:</p>
            <ul className="mt-2 list-disc space-y-1.5 pl-5">
              <li>
                Upload content that you do not have the right to use or that
                violates any law
              </li>
              <li>
                Use the Service in a way that violates your professional
                obligations or licensing requirements
              </li>
              <li>
                Reverse engineer, decompile, or attempt to extract source code
                from the platform
              </li>
              <li>
                Use automated tools to scrape, overload, or abuse the Service
              </li>
              <li>
                Resell, sublicense, or provide access to the Service to
                unauthorized third parties
              </li>
            </ul>
          </section>

          {/* 7 */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900">
              7. Professional Responsibility
            </h2>
            <p className="mt-3">
              Callwen is a tool to assist financial professionals — it does NOT
              provide professional advice. AI-generated analysis, summaries, and
              recommendations are informational only and should not be relied
              upon as a substitute for professional judgment.
            </p>
            <p className="mt-3">
              You are obligated to verify all AI-generated content before
              incorporating it into client deliverables, tax returns, or other
              professional work product. You remain responsible for compliance
              with all applicable professional standards, including IRC Section
              7216 requirements regarding taxpayer consent for disclosure and
              use of tax return information.
            </p>
          </section>

          {/* 8 */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900">
              8. Intellectual Property
            </h2>
            <p className="mt-3">
              The Callwen platform, including its design, features, code, and
              documentation, is owned by Callwen, Inc. and protected by
              applicable intellectual property laws. Your subscription grants
              you a limited, non-exclusive, non-transferable license to use the
              Service.
            </p>
            <p className="mt-3">
              If you provide feedback, suggestions, or feature requests, you
              grant us a perpetual, royalty-free license to use that feedback to
              improve the Service.
            </p>
          </section>

          {/* 9 */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900">
              9. Disclaimers
            </h2>
            <p className="mt-3 uppercase font-medium text-gray-900">
              THE SERVICE IS PROVIDED &quot;AS IS&quot; AND &quot;AS
              AVAILABLE&quot; WITHOUT WARRANTIES OF ANY KIND, WHETHER EXPRESS OR
              IMPLIED, INCLUDING BUT NOT LIMITED TO IMPLIED WARRANTIES OF
              MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND
              NON-INFRINGEMENT. CALLWEN DOES NOT WARRANT THAT AI-GENERATED
              CONTENT WILL BE ACCURATE, COMPLETE, OR SUITABLE FOR ANY
              PARTICULAR PURPOSE. YOU USE AI-GENERATED CONTENT AT YOUR OWN
              RISK.
            </p>
          </section>

          {/* 10 */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900">
              10. Limitation of Liability
            </h2>
            <p className="mt-3 uppercase font-medium text-gray-900">
              TO THE MAXIMUM EXTENT PERMITTED BY LAW, CALLWEN&apos;S TOTAL
              LIABILITY TO YOU FOR ALL CLAIMS ARISING FROM OR RELATED TO THE
              SERVICE SHALL NOT EXCEED THE TOTAL FEES YOU PAID TO CALLWEN IN
              THE TWELVE (12) MONTHS PRECEDING THE CLAIM.
            </p>
            <p className="mt-3 uppercase font-medium text-gray-900">
              IN NO EVENT SHALL CALLWEN BE LIABLE FOR ANY INDIRECT, INCIDENTAL,
              SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES, INCLUDING BUT NOT
              LIMITED TO LOSS OF PROFITS, DATA, BUSINESS OPPORTUNITIES, OR
              GOODWILL, REGARDLESS OF WHETHER SUCH DAMAGES WERE FORESEEABLE.
            </p>
          </section>

          {/* 11 */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900">
              11. Indemnification
            </h2>
            <p className="mt-3">
              You agree to indemnify and hold harmless Callwen, Inc., its
              officers, directors, employees, and agents from any claims,
              damages, losses, or expenses (including reasonable
              attorneys&apos; fees) arising from your use of the Service, your
              violation of these Terms, or your violation of any third-party
              rights.
            </p>
          </section>

          {/* 12 */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900">
              12. Dispute Resolution
            </h2>
            <p className="mt-3">
              These Terms are governed by the laws of the State of Florida,
              without regard to conflict of law principles. Any disputes arising
              from these Terms or the Service shall be resolved in the state or
              federal courts located in Broward County, Florida.
            </p>
            <p className="mt-3">
              Before filing any formal legal proceeding, you agree to attempt to
              resolve the dispute informally by contacting us at{" "}
              <a
                href="mailto:support@callwen.com"
                className="text-blue-600 hover:underline"
              >
                support@callwen.com
              </a>
              . We will attempt to resolve the dispute within 30 days.
            </p>
          </section>

          {/* 13 */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900">
              13. Changes to These Terms
            </h2>
            <p className="mt-3">
              We may update these Terms from time to time. For material changes,
              we will provide at least 30 days&apos; notice via email or a
              prominent notice on the platform. Your continued use of the
              Service after changes take effect constitutes acceptance of the
              revised Terms.
            </p>
          </section>

          {/* 14 */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900">
              14. General
            </h2>
            <ul className="mt-3 list-disc space-y-1.5 pl-5">
              <li>
                <strong>Severability:</strong> If any provision of these Terms
                is found unenforceable, the remaining provisions remain in full
                force and effect.
              </li>
              <li>
                <strong>Entire Agreement:</strong> These Terms, together with
                the Privacy Policy, constitute the entire agreement between you
                and Callwen regarding the Service.
              </li>
              <li>
                <strong>Waiver:</strong> Failure to enforce any provision of
                these Terms does not constitute a waiver of that provision.
              </li>
              <li>
                <strong>Assignment:</strong> You may not assign your rights
                under these Terms without our prior written consent. We may
                assign our rights without restriction.
              </li>
            </ul>
          </section>

          {/* 15 */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900">
              15. Contact Us
            </h2>
            <p className="mt-3">
              If you have questions about these Terms, contact us at:
            </p>
            <ul className="mt-2 space-y-1">
              <li>
                Email:{" "}
                <a
                  href="mailto:support@callwen.com"
                  className="text-blue-600 hover:underline"
                >
                  support@callwen.com
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
