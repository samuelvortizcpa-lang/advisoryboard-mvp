export const CONFIG = {
  API_BASE_URL: 'https://advisoryboard-mvp-production.up.railway.app',
  CLERK_FRONTEND_API: 'https://callwen.com/__clerk',
  APP_URL: 'https://callwen.com',
  MAX_FILE_SIZE: 50 * 1024 * 1024, // 50MB
  MAX_TEXT_LENGTH: 500000, // 500K characters
  CAPTURE_TYPES: ['text_selection', 'full_page', 'file_url', 'screenshot'],
  DOCUMENT_TAGS: [
    { value: 'tax_document', label: 'Tax Document' },
    { value: 'financial_statement', label: 'Financial Statement' },
    { value: 'meeting_notes', label: 'Meeting Notes' },
    { value: 'correspondence', label: 'Correspondence' },
    { value: 'contract', label: 'Contract / Engagement Letter' },
    { value: 'bank_statement', label: 'Bank Statement' },
    { value: 'other', label: 'Other' },
  ],
};
