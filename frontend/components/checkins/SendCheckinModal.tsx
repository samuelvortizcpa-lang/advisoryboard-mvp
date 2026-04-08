"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect, useState } from "react";

import {
  CheckinTemplate,
  CheckinQuestion,
  createCheckinsApi,
} from "@/lib/api";

// ─── Types ────────────────────────────────────────────────────────────────────

interface SendCheckinModalProps {
  clientId: string;
  clientName: string;
  clientEmail: string | null;
  onClose: () => void;
  onSent: () => void;
}

type Step = "choose" | "review";

// ─── Component ───────────────────────────────────────────────────────────────

export default function SendCheckinModal({
  clientId,
  clientName,
  clientEmail,
  onClose,
  onSent,
}: SendCheckinModalProps) {
  const { getToken } = useAuth();

  const [step, setStep] = useState<Step>("choose");
  const [templates, setTemplates] = useState<CheckinTemplate[]>([]);
  const [templatesLoading, setTemplatesLoading] = useState(true);
  const [selectedTemplate, setSelectedTemplate] = useState<CheckinTemplate | null>(null);
  const [showManageModal, setShowManageModal] = useState(false);

  // Send form
  const [toEmail, setToEmail] = useState(clientEmail ?? "");
  const [toName, setToName] = useState(clientName ?? "");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 3000);
    return () => clearTimeout(t);
  }, [toast]);

  // Fetch templates on mount
  useEffect(() => {
    let cancelled = false;
    setTemplatesLoading(true);
    createCheckinsApi(getToken)
      .getTemplates()
      .then((t) => {
        if (!cancelled) setTemplates(t.filter((tpl) => tpl.is_active));
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setTemplatesLoading(false);
      });
    return () => { cancelled = true; };
  }, [getToken]);

  function selectTemplate(tpl: CheckinTemplate) {
    setSelectedTemplate(tpl);
    setStep("review");
    setError(null);
  }

  async function handleSend() {
    if (!selectedTemplate || !toEmail.trim()) return;
    setSending(true);
    setError(null);

    try {
      await createCheckinsApi(getToken).sendCheckin(clientId, {
        template_id: selectedTemplate.id,
        client_email: toEmail.trim(),
        client_name: toName.trim() || undefined,
      });
      setToast(`Check-in sent to ${toEmail.trim()}`);
      onSent();
      setTimeout(() => onClose(), 1200);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to send check-in";
      if (msg.toLowerCase().includes("limit") || msg.toLowerCase().includes("upgrade")) {
        setError("You've reached your plan's check-in limit. Upgrade to send more.");
      } else {
        setError(msg);
      }
    } finally {
      setSending(false);
    }
  }

  const systemTemplates = templates.filter((t) => t.is_default);
  const customTemplates = templates.filter((t) => !t.is_default);

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-40 bg-black/30" onClick={onClose} />

      {/* Slide-over panel */}
      <div className="fixed inset-y-0 right-0 z-50 flex w-full max-w-lg flex-col bg-white shadow-2xl animate-slide-in-right">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Send Check-in</h2>
            <p className="text-xs text-gray-500">To {clientName}</p>
          </div>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-6 py-5">
          {step === "choose" && (
            <div>
              <p className="mb-4 text-sm text-gray-600">
                Choose a check-in template to send to your client.
              </p>

              {templatesLoading ? (
                <div className="flex items-center justify-center py-12">
                  <SmallSpinner />
                  <span className="ml-2 text-sm text-gray-500">Loading templates...</span>
                </div>
              ) : (
                <>
                  {systemTemplates.length > 0 && (
                    <div className="mb-5">
                      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-400">Default Templates</h3>
                      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                        {systemTemplates.map((tpl) => (
                          <TemplateCard key={tpl.id} template={tpl} isDefault onClick={() => selectTemplate(tpl)} />
                        ))}
                      </div>
                    </div>
                  )}

                  {customTemplates.length > 0 && (
                    <div className="mb-5">
                      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-400">Custom Templates</h3>
                      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                        {customTemplates.map((tpl) => (
                          <TemplateCard key={tpl.id} template={tpl} isDefault={false} onClick={() => selectTemplate(tpl)} />
                        ))}
                      </div>
                    </div>
                  )}

                  {templates.length === 0 && (
                    <div className="rounded-xl border border-dashed border-gray-300 p-8 text-center">
                      <p className="text-sm text-gray-500">No templates available.</p>
                    </div>
                  )}

                  <button
                    onClick={() => setShowManageModal(true)}
                    className="mt-2 text-sm font-medium text-[#5bb8af] hover:text-[#4a9e96]"
                  >
                    Manage Templates
                  </button>
                </>
              )}
            </div>
          )}

          {step === "review" && selectedTemplate && (
            <div>
              <button
                onClick={() => { setStep("choose"); setError(null); }}
                className="mb-4 inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
                </svg>
                Back to templates
              </button>

              <h3 className="mb-1 text-sm font-semibold text-gray-900">{selectedTemplate.name}</h3>
              {selectedTemplate.description && (
                <p className="mb-4 text-xs text-gray-500">{selectedTemplate.description}</p>
              )}

              {/* Preview questions */}
              <div className="mb-6 rounded-xl border border-gray-200 bg-gray-50 p-4">
                <h4 className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-400">Questions Preview</h4>
                <ol className="space-y-2">
                  {selectedTemplate.questions.map((q, i) => (
                    <li key={q.id} className="flex gap-2 text-sm">
                      <span className="shrink-0 text-gray-400">{i + 1}.</span>
                      <div>
                        <span className="text-gray-700">{q.text}</span>
                        <span className="ml-2 rounded bg-gray-200 px-1.5 py-0.5 text-[10px] font-medium text-gray-500">{q.type}</span>
                      </div>
                    </li>
                  ))}
                </ol>
              </div>

              {/* Send form */}
              <div className="space-y-3">
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-700">To (email)</label>
                  <input
                    type="email"
                    value={toEmail}
                    onChange={(e) => setToEmail(e.target.value)}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-[#5bb8af] focus:outline-none focus:ring-1 focus:ring-[#5bb8af]"
                    placeholder="client@example.com"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-700">Recipient name</label>
                  <input
                    type="text"
                    value={toName}
                    onChange={(e) => setToName(e.target.value)}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-[#5bb8af] focus:outline-none focus:ring-1 focus:ring-[#5bb8af]"
                    placeholder="Client name"
                  />
                </div>
              </div>

              {error && (
                <div className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">
                  {error}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        {step === "review" && (
          <div className="border-t border-gray-200 px-6 py-4">
            <button
              onClick={handleSend}
              disabled={sending || !toEmail.trim()}
              className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-[#5bb8af] px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-[#4a9e96] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {sending ? (
                <>
                  <SmallSpinner />
                  Sending...
                </>
              ) : (
                <>
                  <SendIcon />
                  Send Check-in
                </>
              )}
            </button>
          </div>
        )}

        {/* Toast */}
        {toast && (
          <div className="absolute bottom-20 left-1/2 -translate-x-1/2 rounded-lg bg-gray-900 px-4 py-2 text-sm text-white shadow-lg">
            {toast}
          </div>
        )}
      </div>

      {/* Manage templates modal */}
      {showManageModal && (
        <ManageTemplatesModal
          onClose={() => setShowManageModal(false)}
          onChanged={() => {
            // Refresh template list
            createCheckinsApi(getToken)
              .getTemplates()
              .then((t) => setTemplates(t.filter((tpl) => tpl.is_active)))
              .catch(() => {});
          }}
        />
      )}

      <style dangerouslySetInnerHTML={{ __html: `
        @keyframes slide-in-right {
          from { transform: translateX(100%); }
          to { transform: translateX(0); }
        }
        .animate-slide-in-right {
          animation: slide-in-right 0.2s ease-out;
        }
      `}} />
    </>
  );
}

// ─── Template Card ──────────────────────────────────────────────────────────

function TemplateCard({
  template,
  isDefault,
  onClick,
}: {
  template: CheckinTemplate;
  isDefault: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="group flex flex-col rounded-xl border border-gray-200 bg-white p-4 text-left transition-all hover:border-[#5bb8af] hover:shadow-md"
    >
      <div className="flex items-start justify-between">
        <h4 className="text-sm font-semibold text-gray-900 group-hover:text-[#5bb8af]">
          {template.name}
        </h4>
        {isDefault && (
          <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-medium text-gray-500">
            Default
          </span>
        )}
      </div>
      {template.description && (
        <p className="mt-1 line-clamp-2 text-xs text-gray-500">{template.description}</p>
      )}
      <p className="mt-2 text-xs text-gray-400">
        {template.questions.length} question{template.questions.length !== 1 ? "s" : ""}
      </p>
    </button>
  );
}

// ─── Manage Templates Modal ─────────────────────────────────────────────────

function ManageTemplatesModal({
  onClose,
  onChanged,
}: {
  onClose: () => void;
  onChanged: () => void;
}) {
  const { getToken } = useAuth();
  const [templates, setTemplates] = useState<CheckinTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<CheckinTemplate | "new" | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);

  useEffect(() => {
    fetchTemplates();
  }, []);

  function fetchTemplates() {
    setLoading(true);
    createCheckinsApi(getToken)
      .getTemplates()
      .then((t) => setTemplates(t))
      .catch(() => {})
      .finally(() => setLoading(false));
  }

  async function handleDelete(id: string) {
    try {
      await createCheckinsApi(getToken).deleteTemplate(id);
      setDeleteConfirm(null);
      fetchTemplates();
      onChanged();
    } catch {}
  }

  return (
    <>
      <div className="fixed inset-0 z-[60] bg-black/20" onClick={onClose} />
      <div className="fixed inset-0 z-[70] flex items-center justify-center p-4">
        <div className="w-full max-w-xl rounded-xl bg-white shadow-2xl">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
            <h2 className="text-base font-semibold text-gray-900">Manage Templates</h2>
            <button onClick={onClose} className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600">
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <div className="max-h-[60vh] overflow-y-auto px-6 py-4">
            {editing ? (
              <TemplateEditor
                template={editing === "new" ? null : editing}
                onSave={() => {
                  setEditing(null);
                  fetchTemplates();
                  onChanged();
                }}
                onCancel={() => setEditing(null)}
              />
            ) : (
              <>
                {loading ? (
                  <div className="flex items-center justify-center py-8">
                    <SmallSpinner />
                  </div>
                ) : (
                  <div className="space-y-2">
                    {templates.map((tpl) => (
                      <div
                        key={tpl.id}
                        className="flex items-center justify-between rounded-lg border border-gray-200 px-4 py-3"
                      >
                        <div className="flex items-center gap-3">
                          {tpl.is_default ? (
                            <LockIcon />
                          ) : (
                            <TemplateDocIcon />
                          )}
                          <div>
                            <p className="text-sm font-medium text-gray-900">{tpl.name}</p>
                            <p className="text-xs text-gray-500">
                              {tpl.questions.length} question{tpl.questions.length !== 1 ? "s" : ""}
                              {tpl.is_default && " · System default"}
                            </p>
                          </div>
                        </div>
                        {!tpl.is_default && (
                          <div className="flex gap-1">
                            <button
                              onClick={() => setEditing(tpl)}
                              className="rounded-md p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
                              title="Edit"
                            >
                              <PencilIcon />
                            </button>
                            {deleteConfirm === tpl.id ? (
                              <div className="flex items-center gap-1">
                                <button
                                  onClick={() => handleDelete(tpl.id)}
                                  className="rounded-md bg-red-50 px-2 py-1 text-xs font-medium text-red-600 hover:bg-red-100"
                                >
                                  Confirm
                                </button>
                                <button
                                  onClick={() => setDeleteConfirm(null)}
                                  className="rounded-md px-2 py-1 text-xs text-gray-500 hover:bg-gray-100"
                                >
                                  Cancel
                                </button>
                              </div>
                            ) : (
                              <button
                                onClick={() => setDeleteConfirm(tpl.id)}
                                className="rounded-md p-1.5 text-gray-400 hover:bg-red-50 hover:text-red-500"
                                title="Delete"
                              >
                                <TrashIcon />
                              </button>
                            )}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                <button
                  onClick={() => setEditing("new")}
                  className="mt-4 inline-flex items-center gap-2 rounded-lg bg-[#5bb8af] px-4 py-2 text-sm font-medium text-white hover:bg-[#4a9e96]"
                >
                  <PlusIcon />
                  Create Template
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

// ─── Template Editor ────────────────────────────────────────────────────────

function TemplateEditor({
  template,
  onSave,
  onCancel,
}: {
  template: CheckinTemplate | null;
  onSave: () => void;
  onCancel: () => void;
}) {
  const { getToken } = useAuth();
  const [name, setName] = useState(template?.name ?? "");
  const [description, setDescription] = useState(template?.description ?? "");
  const [questions, setQuestions] = useState<CheckinQuestion[]>(
    template?.questions ?? [{ id: crypto.randomUUID(), text: "", type: "textarea" }]
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function addQuestion() {
    setQuestions([...questions, { id: crypto.randomUUID(), text: "", type: "textarea" }]);
  }

  function updateQuestion(idx: number, updates: Partial<CheckinQuestion>) {
    setQuestions(questions.map((q, i) => (i === idx ? { ...q, ...updates } : q)));
  }

  function removeQuestion(idx: number) {
    if (questions.length <= 1) return;
    setQuestions(questions.filter((_, i) => i !== idx));
  }

  function moveQuestion(idx: number, dir: -1 | 1) {
    const target = idx + dir;
    if (target < 0 || target >= questions.length) return;
    const next = [...questions];
    [next[idx], next[target]] = [next[target], next[idx]];
    setQuestions(next);
  }

  async function handleSave() {
    if (!name.trim()) { setError("Template name is required"); return; }
    const validQuestions = questions.filter((q) => q.text.trim());
    if (validQuestions.length === 0) { setError("At least one question is required"); return; }

    setSaving(true);
    setError(null);

    try {
      const api = createCheckinsApi(getToken);
      const data = {
        name: name.trim(),
        description: description.trim() || undefined,
        questions: validQuestions,
      };
      if (template) {
        await api.updateTemplate(template.id, data);
      } else {
        await api.createTemplate(data);
      }
      onSave();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to save template");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <h3 className="mb-4 text-sm font-semibold text-gray-900">
        {template ? "Edit Template" : "New Template"}
      </h3>

      <div className="space-y-3">
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-700">Template Name</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-[#5bb8af] focus:outline-none focus:ring-1 focus:ring-[#5bb8af]"
            placeholder="e.g. Quarterly Review Check-in"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-700">Description (optional)</label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={2}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-[#5bb8af] focus:outline-none focus:ring-1 focus:ring-[#5bb8af]"
            placeholder="Brief description of this template's purpose"
          />
        </div>

        <div>
          <label className="mb-2 block text-xs font-semibold uppercase tracking-wider text-gray-400">Questions</label>
          <div className="space-y-2">
            {questions.map((q, i) => (
              <div key={q.id} className="flex items-start gap-2 rounded-lg border border-gray-200 bg-gray-50 p-3">
                <div className="flex shrink-0 flex-col gap-0.5 pt-1">
                  <button
                    onClick={() => moveQuestion(i, -1)}
                    disabled={i === 0}
                    className="rounded p-0.5 text-gray-400 hover:text-gray-600 disabled:opacity-30"
                    title="Move up"
                  >
                    <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 15.75l7.5-7.5 7.5 7.5" />
                    </svg>
                  </button>
                  <button
                    onClick={() => moveQuestion(i, 1)}
                    disabled={i === questions.length - 1}
                    className="rounded p-0.5 text-gray-400 hover:text-gray-600 disabled:opacity-30"
                    title="Move down"
                  >
                    <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
                    </svg>
                  </button>
                </div>
                <div className="flex-1 space-y-2">
                  <input
                    type="text"
                    value={q.text}
                    onChange={(e) => updateQuestion(i, { text: e.target.value })}
                    className="w-full rounded-md border border-gray-300 px-2.5 py-1.5 text-sm focus:border-[#5bb8af] focus:outline-none focus:ring-1 focus:ring-[#5bb8af]"
                    placeholder={`Question ${i + 1}`}
                  />
                  <div className="flex items-center gap-2">
                    <select
                      value={q.type}
                      onChange={(e) => updateQuestion(i, { type: e.target.value, options: e.target.value === "select" || e.target.value === "multiselect" ? [] : undefined })}
                      className="rounded-md border border-gray-300 px-2 py-1 text-xs text-gray-600 focus:border-[#5bb8af] focus:outline-none"
                    >
                      <option value="text">Short text</option>
                      <option value="textarea">Long text</option>
                      <option value="rating">Rating (1-5)</option>
                      <option value="select">Single select</option>
                      <option value="multiselect">Multi select</option>
                    </select>
                  </div>
                  {(q.type === "select" || q.type === "multiselect") && (
                    <input
                      type="text"
                      value={q.options?.join(", ") ?? ""}
                      onChange={(e) => updateQuestion(i, { options: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })}
                      className="w-full rounded-md border border-gray-300 px-2.5 py-1.5 text-xs focus:border-[#5bb8af] focus:outline-none focus:ring-1 focus:ring-[#5bb8af]"
                      placeholder="Options (comma-separated): Option A, Option B, Option C"
                    />
                  )}
                </div>
                <button
                  onClick={() => removeQuestion(i)}
                  disabled={questions.length <= 1}
                  className="shrink-0 rounded-md p-1 text-gray-400 hover:bg-red-50 hover:text-red-500 disabled:opacity-30"
                  title="Remove question"
                >
                  <TrashIcon />
                </button>
              </div>
            ))}
          </div>
          <button
            onClick={addQuestion}
            className="mt-2 inline-flex items-center gap-1 text-sm font-medium text-[#5bb8af] hover:text-[#4a9e96]"
          >
            <PlusIcon />
            Add Question
          </button>
        </div>
      </div>

      {error && (
        <div className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">{error}</div>
      )}

      <div className="mt-4 flex justify-end gap-2">
        <button
          onClick={onCancel}
          className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
        >
          Cancel
        </button>
        <button
          onClick={handleSave}
          disabled={saving}
          className="inline-flex items-center gap-2 rounded-lg bg-[#5bb8af] px-4 py-2 text-sm font-medium text-white hover:bg-[#4a9e96] disabled:opacity-50"
        >
          {saving && <SmallSpinner />}
          {template ? "Update Template" : "Save Template"}
        </button>
      </div>
    </div>
  );
}

// ─── Icons ──────────────────────────────────────────────────────────────────

function SmallSpinner() {
  return (
    <span className="block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
  );
}

function SendIcon() {
  return (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
    </svg>
  );
}

function PencilIcon() {
  return (
    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L6.832 19.82a4.5 4.5 0 01-1.897 1.13l-2.685.8.8-2.685a4.5 4.5 0 011.13-1.897L16.863 4.487zm0 0L19.5 7.125" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
    </svg>
  );
}

function LockIcon() {
  return (
    <svg className="h-4 w-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z" />
    </svg>
  );
}

function TemplateDocIcon() {
  return (
    <svg className="h-4 w-4 text-[#5bb8af]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
    </svg>
  );
}
