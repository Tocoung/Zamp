/**
 * Centralized API client and configuration for Zamp Vendor Onboarding
 */

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

export interface HealthStatus {
  status: 'healthy' | 'degraded' | 'offline';
  timestamp: string;
  environment: string;
  version: string;
  database: 'connected' | 'disconnected' | 'unknown';
}

export interface VendorCreatePayload {
  legal_name: string;
  trade_name?: string;
  business_type: string;
  country_of_incorporation: string;
  registration_number: string;

  contact_name: string;
  contact_email: string;
  contact_phone: string;

  address_line1: string;
  address_line2?: string;
  city: string;
  state_province: string;
  postal_code: string;
  address_country: string;

  tax_id_type: string;
  tax_id_number: string;

  bank_account_holder_name: string;
  bank_name: string;
  bank_account_number: string;
  bank_routing_number: string;
  bank_country: string;
}

export interface VendorResponse {
  id: string;
  legal_name: string;
  trade_name?: string | null;
  business_type: string;
  country_of_incorporation: string;
  registration_number: string;

  contact_name: string;
  contact_email: string;
  contact_phone: string;

  address_line1: string;
  address_line2?: string | null;
  city: string;
  state_province: string;
  postal_code: string;
  address_country: string;

  tax_id_type: string;
  tax_id_number: string;

  bank_account_holder_name: string;
  bank_name: string;
  bank_routing_number: string;
  bank_country: string;
  bank_account_number_masked: string;

  status: string;
  created_at: string;
  updated_at: string;
}

export interface VendorSummary {
  id: string;
  legal_name: string;
  trade_name?: string | null;
  business_type: string;
  country_of_incorporation: string;
  contact_email: string;
  status: string;
  created_at: string;
}

export interface VendorPagination {
  items: VendorSummary[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export async function fetchHealthStatus(): Promise<HealthStatus> {
  try {
    const response = await fetch(`${API_BASE_URL}/health`, {
      method: 'GET',
      headers: {
        Accept: 'application/json',
      },
    });

    if (!response.ok && response.status !== 503) {
      throw new Error(`API returned HTTP ${response.status}`);
    }

    const data = await response.json();
    return {
      status: data.status,
      timestamp: data.timestamp,
      environment: data.environment,
      version: data.version,
      database: data.database,
    };
  } catch (error) {
    return {
      status: 'offline',
      timestamp: new Date().toISOString(),
      environment: 'unknown',
      version: 'unknown',
      database: 'unknown',
    };
  }
}

export async function createVendor(
  payload: VendorCreatePayload
): Promise<VendorResponse> {
  const response = await fetch(`${API_BASE_URL}/vendors`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    let errorMessage = `Failed to create vendor (HTTP ${response.status})`;
    try {
      const errData = await response.json();
      if (errData.detail) {
        if (Array.isArray(errData.detail)) {
          errorMessage = errData.detail
            .map((e: any) => `${e.loc?.slice(-1)[0] || 'Field'}: ${e.msg}`)
            .join('; ');
        } else {
          errorMessage = errData.detail;
        }
      }
    } catch {
      // fallback
    }
    throw new Error(errorMessage);
  }

  return response.json();
}

export async function fetchVendors(
  page = 1,
  pageSize = 10,
  status?: string,
  search?: string
): Promise<VendorPagination> {
  const params = new URLSearchParams({
    page: page.toString(),
    page_size: pageSize.toString(),
  });
  if (status && status !== 'ALL') {
    params.append('status', status);
  }
  if (search && search.trim()) {
    params.append('search', search.trim());
  }

  const response = await fetch(
    `${API_BASE_URL}/vendors?${params.toString()}`,
    {
      method: 'GET',
      headers: {
        Accept: 'application/json',
      },
    }
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch vendors (HTTP ${response.status})`);
  }

  return response.json();
}

export async function fetchVendorById(
  vendorId: string
): Promise<VendorResponse> {
  const response = await fetch(`${API_BASE_URL}/vendors/${vendorId}`, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    if (response.status === 404) {
      throw new Error('Vendor not found');
    }
    throw new Error(`Failed to fetch vendor details (HTTP ${response.status})`);
  }

  return response.json();
}

export interface ValidationFinding {
  rule_id: string;
  field: string;
  severity: 'ERROR' | 'WARNING' | 'INFO';
  status: string;
  code: string;
  message: string;
  suggestion?: string | null;
}

export interface ValidationSummary {
  total_checks: number;
  passed: number;
  failed: number;
  warnings: number;
  info: number;
}

export interface ValidationResult {
  validation_id: string;
  vendor_id?: string | null;
  status: 'PASSED' | 'PASSED_WITH_WARNINGS' | 'FAILED';
  valid: boolean;
  summary: ValidationSummary;
  findings: ValidationFinding[];
  validated_at: string;
  ruleset_version: string;
}

export async function validateVendorPayload(
  payload: Partial<VendorCreatePayload>
): Promise<ValidationResult> {
  const response = await fetch(`${API_BASE_URL}/vendors/validate`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    let errorMessage = `Validation request failed (HTTP ${response.status})`;
    try {
      const errData = await response.json();
      if (errData.detail) errorMessage = errData.detail;
    } catch {
      // fallback
    }
    throw new Error(errorMessage);
  }

  return response.json();
}

export async function validateExistingVendor(
  vendorId: string
): Promise<ValidationResult> {
  const response = await fetch(`${API_BASE_URL}/vendors/${vendorId}/validate`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    if (response.status === 404) {
      throw new Error(`Vendor with ID '${vendorId}' not found`);
    }
    let errorMessage = `Failed to validate vendor (HTTP ${response.status})`;
    try {
      const errData = await response.json();
      if (errData.detail) errorMessage = errData.detail;
    } catch {
      // fallback
    }
    throw new Error(errorMessage);
  }

  return response.json();
}

export type DecisionStatus = 'APPROVED' | 'PENDING' | 'REJECTED';

export interface DecisionReason {
  code: string;
  title: string;
  explanation: string;
  source_rule_id?: string | null;
  source_finding_code?: string | null;
  severity: string;
}

export interface DecisionRecommendation {
  action: string;
  description: string;
  priority: 'HIGH' | 'MEDIUM' | 'LOW';
}

export interface DecisionResult {
  decision_id: string;
  vendor_id: string;
  status: DecisionStatus;
  decision_version: string;
  ruleset_version: string;
  validation_id: string;
  validation_status: string;
  reason_codes: string[];
  reasons: DecisionReason[];
  recommendations: DecisionRecommendation[];
  validation_snapshot?: any;
  decided_at: string;
}

export interface DecisionHistoryItem {
  id: string;
  vendor_id: string;
  status: DecisionStatus;
  decision_version: string;
  ruleset_version: string;
  validation_id: string;
  reason_codes: string[];
  reasons: DecisionReason[];
  recommendations: DecisionRecommendation[];
  decided_at: string;
}

export interface DecisionHistoryPagination {
  items: DecisionHistoryItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export async function runVendorDecision(
  vendorId: string
): Promise<DecisionResult> {
  const response = await fetch(`${API_BASE_URL}/vendors/${vendorId}/decide`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    if (response.status === 404) {
      throw new Error(`Vendor with ID '${vendorId}' not found`);
    }
    let errorMessage = `Failed to compute decision (HTTP ${response.status})`;
    try {
      const errData = await response.json();
      if (errData.detail) errorMessage = errData.detail;
    } catch {
      // fallback
    }
    throw new Error(errorMessage);
  }

  return response.json();
}

export async function getLatestDecision(
  vendorId: string
): Promise<DecisionResult | null> {
  const response = await fetch(`${API_BASE_URL}/vendors/${vendorId}/decision`, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
    },
  });

  if (response.status === 404) {
    return null;
  }

  if (!response.ok) {
    throw new Error(`Failed to fetch latest decision (HTTP ${response.status})`);
  }

  return response.json();
}

export async function getDecisionHistory(
  vendorId: string,
  page = 1,
  pageSize = 10
): Promise<DecisionHistoryPagination> {
  const response = await fetch(
    `${API_BASE_URL}/vendors/${vendorId}/decision-history?page=${page}&page_size=${pageSize}`,
    {
      method: 'GET',
      headers: {
        Accept: 'application/json',
      },
    }
  );

  if (!response.ok) {
    if (response.status === 404) {
      throw new Error(`Vendor with ID '${vendorId}' not found`);
    }
    throw new Error(`Failed to fetch decision history (HTTP ${response.status})`);
  }

  return response.json();
}

export interface VendorActivityItem {
  id: string;
  vendor_id: string;
  event_type: string;
  title: string;
  description: string;
  status?: string | null;
  created_at: string;
}

export interface VendorActivityPagination {
  items: VendorActivityItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export async function fetchVendorActivities(
  vendorId: string,
  page = 1,
  pageSize = 20
): Promise<VendorActivityPagination> {
  const response = await fetch(
    `${API_BASE_URL}/vendors/${vendorId}/activities?page=${page}&page_size=${pageSize}`,
    {
      method: 'GET',
      headers: {
        Accept: 'application/json',
      },
    }
  );

  if (!response.ok) {
    if (response.status === 404) {
      throw new Error(`Vendor with ID '${vendorId}' not found`);
    }
    throw new Error(`Failed to fetch vendor activities (HTTP ${response.status})`);
  }

  return response.json();
}

export async function updateVendor(
  vendorId: string,
  payload: Partial<VendorCreatePayload>
): Promise<VendorResponse> {
  const response = await fetch(`${API_BASE_URL}/vendors/${vendorId}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    if (response.status === 404) {
      throw new Error(`Vendor with ID '${vendorId}' not found`);
    }
    let errorMessage = `Failed to update vendor (HTTP ${response.status})`;
    try {
      const errData = await response.json();
      if (errData.detail) errorMessage = errData.detail;
    } catch {
      // fallback
    }
    throw new Error(errorMessage);
  }

  return response.json();
}

// ==========================================
// Phase 2, Step 1: Document Management Types & API
// ==========================================

export type DocumentCategory =
  | 'CERTIFICATE_OF_INCORPORATION'
  | 'TAX_CERTIFICATE'
  | 'BANK_PROOF'
  | 'ADDRESS_PROOF'
  | 'OTHER'
  | 'UNKNOWN';

export interface VendorDocumentResponse {
  id: string;
  vendor_id: string;
  original_filename: string;
  sanitized_filename: string;
  document_category: DocumentCategory | string;
  mime_type: string;
  file_extension: string;
  file_size_bytes: number;
  sha256_checksum: string;
  upload_status: string;
  document_version: number;
  created_at: string;
  updated_at: string;
  latest_classification?: DocumentClassificationResponse | null;
  latest_extraction?: DocumentExtractionResponse | null;
}

export type ClassificationStatus =
  | 'CLASSIFIED'
  | 'LOW_CONFIDENCE'
  | 'INSUFFICIENT_TEXT'
  | 'FAILED';

export interface ClassificationEvidence {
  matched_headings?: string[];
  matched_keywords?: string[];
  signals_by_category?: Record<string, { heading_matches?: string[]; keyword_matches?: string[]; total_score?: number }>;
  pages_inspected?: number;
  chars_inspected?: number;
  [key: string]: unknown;
}

export interface DocumentClassificationResponse {
  id: string;
  document_id: string;
  vendor_id: string;
  declared_category: DocumentCategory | string;
  predicted_category: DocumentCategory | string;
  status: ClassificationStatus;
  confidence_score: number;
  evidence: ClassificationEvidence;
  limitation_code?: string | null;
  limitation_reason?: string | null;
  classifier_version: string;
  classified_at: string;
}

export interface DocumentClassificationHistoryPagination {
  items: DocumentClassificationResponse[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface VendorDocumentPagination {
  items: VendorDocumentResponse[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export async function fetchVendorDocuments(
  vendorId: string,
  category?: string,
  page = 1,
  pageSize = 50
): Promise<VendorDocumentPagination> {
  let url = `${API_BASE_URL}/vendors/${vendorId}/documents?page=${page}&page_size=${pageSize}`;
  if (category) {
    url += `&category=${encodeURIComponent(category)}`;
  }

  const response = await fetch(url, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    if (response.status === 404) {
      throw new Error(`Vendor with ID '${vendorId}' not found`);
    }
    throw new Error(`Failed to fetch documents (HTTP ${response.status})`);
  }

  return response.json();
}

export async function uploadVendorDocument(
  vendorId: string,
  file: File,
  category: DocumentCategory | string = 'OTHER'
): Promise<VendorDocumentResponse> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('document_category', category);

  const response = await fetch(`${API_BASE_URL}/vendors/${vendorId}/documents`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    let errorMsg = `Upload failed (HTTP ${response.status})`;
    try {
      const err = await response.json();
      if (err.detail) {
        errorMsg = typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail);
      }
    } catch {
      // fallback
    }
    throw new Error(errorMsg);
  }

  return response.json();
}

export async function downloadVendorDocument(
  vendorId: string,
  documentId: string,
  filename: string
): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/vendors/${vendorId}/documents/${documentId}/content`,
    {
      method: 'GET',
    }
  );

  if (!response.ok) {
    let errorMsg = `Download failed (HTTP ${response.status})`;
    try {
      const err = await response.json();
      if (err.detail) errorMsg = err.detail;
    } catch {
      // fallback
    }
    throw new Error(errorMsg);
  }

  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.style.display = 'none';
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  window.URL.revokeObjectURL(url);
  document.body.removeChild(a);
}

export async function deleteVendorDocument(
  vendorId: string,
  documentId: string
): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/vendors/${vendorId}/documents/${documentId}`,
    {
      method: 'DELETE',
    }
  );

  if (!response.ok) {
    let errorMsg = `Delete failed (HTTP ${response.status})`;
    try {
      const err = await response.json();
      if (err.detail) errorMsg = err.detail;
    } catch {
      // fallback
    }
    throw new Error(errorMsg);
  }
}

export async function classifyVendorDocument(
  vendorId: string,
  documentId: string
): Promise<DocumentClassificationResponse> {
  const response = await fetch(
    `${API_BASE_URL}/vendors/${vendorId}/documents/${documentId}/classify`,
    {
      method: 'POST',
      headers: {
        Accept: 'application/json',
      },
    }
  );

  if (!response.ok) {
    let errorMsg = `Classification failed (HTTP ${response.status})`;
    try {
      const err = await response.json();
      if (err.detail) {
        errorMsg = typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail);
      }
    } catch {
      // fallback
    }
    throw new Error(errorMsg);
  }

  return response.json();
}

export async function fetchDocumentClassification(
  vendorId: string,
  documentId: string
): Promise<DocumentClassificationResponse> {
  const response = await fetch(
    `${API_BASE_URL}/vendors/${vendorId}/documents/${documentId}/classification`,
    {
      method: 'GET',
      headers: {
        Accept: 'application/json',
      },
    }
  );

  if (!response.ok) {
    let errorMsg = `Failed to fetch classification (HTTP ${response.status})`;
    try {
      const err = await response.json();
      if (err.detail) errorMsg = err.detail;
    } catch {
      // fallback
    }
    throw new Error(errorMsg);
  }

  return response.json();
}

export async function fetchDocumentClassificationHistory(
  vendorId: string,
  documentId: string,
  page = 1,
  pageSize = 20
): Promise<DocumentClassificationHistoryPagination> {
  const response = await fetch(
    `${API_BASE_URL}/vendors/${vendorId}/documents/${documentId}/classification-history?page=${page}&page_size=${pageSize}`,
    {
      method: 'GET',
      headers: {
        Accept: 'application/json',
      },
    }
  );

  if (!response.ok) {
    let errorMsg = `Failed to fetch classification history (HTTP ${response.status})`;
    try {
      const err = await response.json();
      if (err.detail) errorMsg = err.detail;
    } catch {
      // fallback
    }
    throw new Error(errorMsg);
  }

  return response.json();
}




export type FieldStatus = 'EXTRACTED' | 'MISSING' | 'UNREADABLE' | 'NEEDS_REVIEW';

export type ExtractionStatus = 'COMPLETED' | 'PARTIAL' | 'INSUFFICIENT_TEXT' | 'FAILED';

export interface FieldSource {
  document_id: string;
  page_number: number;
  extraction_method: 'DIGITAL_TEXT' | 'OCR';
  evidence_location?: string | null;
  evidence_snippet?: string | null;
}

export interface ExtractedField {
  field_name: string;
  value?: string | null;
  masked_value?: string | null;
  status: FieldStatus;
  confidence?: number | null;
  source: FieldSource;
  limitation_or_reason?: string | null;
}

export interface DocumentExtractionResponse {
  id: string;
  document_id: string;
  vendor_id: string;
  document_category_used: string;
  status: ExtractionStatus;
  fields: Record<string, ExtractedField>;
  extracted_fields_count: number;
  limitation_code?: string | null;
  limitation_reason?: string | null;
  ocr_engine_version: string;
  extracted_at: string;
}

export interface DocumentExtractionHistoryPagination {
  items: DocumentExtractionResponse[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export async function extractVendorDocument(
  vendorId: string,
  documentId: string
): Promise<DocumentExtractionResponse> {
  const response = await fetch(
    `${API_BASE_URL}/vendors/${vendorId}/documents/${documentId}/extract`,
    {
      method: 'POST',
      headers: {
        Accept: 'application/json',
      },
    }
  );

  if (!response.ok) {
    let errorMsg = `Extraction failed (HTTP ${response.status})`;
    try {
      const err = await response.json();
      if (err.detail) {
        errorMsg = typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail);
      }
    } catch {
      // fallback
    }
    throw new Error(errorMsg);
  }

  return response.json();
}

export async function fetchDocumentExtraction(
  vendorId: string,
  documentId: string
): Promise<DocumentExtractionResponse> {
  const response = await fetch(
    `${API_BASE_URL}/vendors/${vendorId}/documents/${documentId}/extraction`,
    {
      method: 'GET',
      headers: {
        Accept: 'application/json',
      },
    }
  );

  if (!response.ok) {
    let errorMsg = `Failed to fetch extraction (HTTP ${response.status})`;
    try {
      const err = await response.json();
      if (err.detail) errorMsg = err.detail;
    } catch {
      // fallback
    }
    throw new Error(errorMsg);
  }

  return response.json();
}

export async function fetchDocumentExtractionHistory(
  vendorId: string,
  documentId: string,
  page = 1,
  pageSize = 20
): Promise<DocumentExtractionHistoryPagination> {
  const response = await fetch(
    `${API_BASE_URL}/vendors/${vendorId}/documents/${documentId}/extraction-history?page=${page}&page_size=${pageSize}`,
    {
      method: 'GET',
      headers: {
        Accept: 'application/json',
      },
    }
  );

  if (!response.ok) {
    let errorMsg = `Failed to fetch extraction history (HTTP ${response.status})`;
    try {
      const err = await response.json();
      if (err.detail) errorMsg = err.detail;
    } catch {
      // fallback
    }
    throw new Error(errorMsg);
  }

  return response.json();
}
