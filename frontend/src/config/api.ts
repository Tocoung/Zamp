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
  pageSize = 10
): Promise<VendorPagination> {
  const response = await fetch(
    `${API_BASE_URL}/vendors?page=${page}&page_size=${pageSize}`,
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
