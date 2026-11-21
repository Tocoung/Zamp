import React from 'react';
import {
  X,
  Building2,
  User,
  MapPin,
  FileText,
  CreditCard,
  Clock,
  Shield,
  ShieldCheck,
  Copy,
  Check,
  Loader2,
  AlertCircle,
} from 'lucide-react';
import { VendorResponse, ValidationResult, validateExistingVendor } from '../config/api';
import { ValidationReport } from './ValidationReport';

interface VendorDetailModalProps {
  vendor: VendorResponse | null;
  isOpen: boolean;
  onClose: () => void;
}

export const VendorDetailModal: React.FC<VendorDetailModalProps> = ({
  vendor,
  isOpen,
  onClose,
}) => {
  const [copied, setCopied] = React.useState(false);
  const [isValidating, setIsValidating] = React.useState(false);
  const [validationResult, setValidationResult] = React.useState<ValidationResult | null>(null);
  const [validationError, setValidationError] = React.useState<string | null>(null);

  if (!isOpen || !vendor) return null;

  const handleCopyId = () => {
    navigator.clipboard.writeText(vendor.id);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleRunValidation = async () => {
    if (!vendor) return;
    setIsValidating(true);
    setValidationError(null);
    try {
      const res = await validateExistingVendor(vendor.id);
      setValidationResult(res);
    } catch (err: any) {
      setValidationError(err.message || 'Validation request failed');
    } finally {
      setIsValidating(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl max-w-3xl w-full shadow-2xl border border-slate-200 overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        {/* Modal Header */}
        <div className="border-b border-slate-200 bg-slate-50/80 px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-sky-100 border border-sky-200 flex items-center justify-center text-sky-700 font-bold">
              <Building2 className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-base font-bold text-slate-900">
                  {vendor.legal_name}
                </h3>
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-sky-50 text-sky-700 border border-sky-200">
                  {vendor.status}
                </span>
              </div>
              <div className="flex items-center gap-2 text-xs text-slate-500 mt-0.5">
                <span className="font-mono">{vendor.id}</span>
                <button
                  type="button"
                  onClick={handleCopyId}
                  className="text-slate-400 hover:text-slate-600 transition-colors"
                  title="Copy Vendor ID"
                >
                  {copied ? (
                    <Check className="w-3.5 h-3.5 text-emerald-600" />
                  ) : (
                    <Copy className="w-3.5 h-3.5" />
                  )}
                </button>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleRunValidation}
              disabled={isValidating}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200 transition-colors disabled:opacity-50"
            >
              {isValidating ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-indigo-600" />
                  <span>Validating...</span>
                </>
              ) : (
                <>
                  <ShieldCheck className="w-3.5 h-3.5 text-indigo-600" />
                  <span>Validate Record</span>
                </>
              )}
            </button>

            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Modal Body */}
        <div className="p-6 space-y-6 max-h-[75vh] overflow-y-auto">
          {/* Validation Report Banner */}
          {validationResult && (
            <ValidationReport
              result={validationResult}
              onClose={() => setValidationResult(null)}
              title="Vendor Record Validation Check"
            />
          )}

          {/* Validation Request Error */}
          {validationError && (
            <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
              <span>{validationError}</span>
            </div>
          )}
          {/* Section 1: Company Identity */}
          <div className="space-y-2">
            <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
              <Building2 className="w-3.5 h-3.5 text-sky-600" />
              Company Identity
            </h4>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 p-3.5 rounded-xl bg-slate-50/70 border border-slate-200/80 text-xs">
              <div>
                <span className="text-slate-500 block">Legal Name</span>
                <span className="font-semibold text-slate-800">{vendor.legal_name}</span>
              </div>
              <div>
                <span className="text-slate-500 block">Trade Name</span>
                <span className="font-semibold text-slate-800">
                  {vendor.trade_name || '—'}
                </span>
              </div>
              <div>
                <span className="text-slate-500 block">Business Type</span>
                <span className="font-semibold text-slate-800">{vendor.business_type}</span>
              </div>
              <div>
                <span className="text-slate-500 block">Country of Incorporation</span>
                <span className="font-semibold text-slate-800">{vendor.country_of_incorporation}</span>
              </div>
              <div className="sm:col-span-2">
                <span className="text-slate-500 block">Registration Number</span>
                <span className="font-mono font-semibold text-slate-800">
                  {vendor.registration_number}
                </span>
              </div>
            </div>
          </div>

          {/* Section 2: Contact Information */}
          <div className="space-y-2">
            <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
              <User className="w-3.5 h-3.5 text-sky-600" />
              Contact Information
            </h4>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 p-3.5 rounded-xl bg-slate-50/70 border border-slate-200/80 text-xs">
              <div>
                <span className="text-slate-500 block">Primary Contact</span>
                <span className="font-semibold text-slate-800">{vendor.contact_name}</span>
              </div>
              <div>
                <span className="text-slate-500 block">Business Email</span>
                <span className="font-mono text-slate-800">{vendor.contact_email}</span>
              </div>
              <div>
                <span className="text-slate-500 block">Phone Number</span>
                <span className="font-semibold text-slate-800">{vendor.contact_phone}</span>
              </div>
            </div>
          </div>

          {/* Section 3: Registered Address */}
          <div className="space-y-2">
            <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
              <MapPin className="w-3.5 h-3.5 text-sky-600" />
              Registered Address
            </h4>
            <div className="p-3.5 rounded-xl bg-slate-50/70 border border-slate-200/80 text-xs space-y-1">
              <div className="font-semibold text-slate-800">
                {vendor.address_line1}
                {vendor.address_line2 ? `, ${vendor.address_line2}` : ''}
              </div>
              <div className="text-slate-600">
                {vendor.city}, {vendor.state_province} {vendor.postal_code}
              </div>
              <div className="text-slate-500 font-medium">
                {vendor.address_country}
              </div>
            </div>
          </div>

          {/* Section 4: Tax Information */}
          <div className="space-y-2">
            <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
              <FileText className="w-3.5 h-3.5 text-sky-600" />
              Tax Information
            </h4>
            <div className="grid grid-cols-2 gap-3 p-3.5 rounded-xl bg-slate-50/70 border border-slate-200/80 text-xs">
              <div>
                <span className="text-slate-500 block">Tax ID Type</span>
                <span className="font-semibold text-slate-800">{vendor.tax_id_type}</span>
              </div>
              <div>
                <span className="text-slate-500 block">Tax Identification Number</span>
                <span className="font-mono font-semibold text-slate-800">
                  {vendor.tax_id_number}
                </span>
              </div>
            </div>
          </div>

          {/* Section 5: Banking Information */}
          <div className="space-y-2">
            <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
              <CreditCard className="w-3.5 h-3.5 text-sky-600" />
              Banking Details (Account Number Encrypted)
            </h4>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 p-3.5 rounded-xl bg-slate-50/70 border border-slate-200/80 text-xs">
              <div>
                <span className="text-slate-500 block">Account Holder</span>
                <span className="font-semibold text-slate-800">
                  {vendor.bank_account_holder_name}
                </span>
              </div>
              <div>
                <span className="text-slate-500 block">Bank Name</span>
                <span className="font-semibold text-slate-800">{vendor.bank_name}</span>
              </div>
              <div>
                <span className="text-slate-500 block">Bank Country</span>
                <span className="font-semibold text-slate-800">{vendor.bank_country}</span>
              </div>
              <div>
                <span className="text-slate-500 block">Account Number</span>
                <span className="font-mono font-bold text-sky-800 bg-sky-50 px-2 py-0.5 rounded border border-sky-200 inline-block">
                  {vendor.bank_account_number_masked}
                </span>
              </div>
              <div className="sm:col-span-2">
                <span className="text-slate-500 block">Routing / SWIFT / IFSC Code</span>
                <span className="font-mono font-semibold text-slate-800">
                  {vendor.bank_routing_number}
                </span>
              </div>
            </div>
            <div className="flex items-center gap-1.5 text-[11px] text-slate-500 px-1">
              <Shield className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
              <span>
                Bank account number is encrypted at rest (AES-128-CBC + HMAC via Fernet) and masked in UI views. Routing numbers and tax IDs are unencrypted.
              </span>
            </div>
          </div>

          {/* Section 6: Metadata */}
          <div className="pt-2 border-t border-slate-100 flex flex-wrap items-center justify-between gap-3 text-[11px] text-slate-400">
            <div className="flex items-center gap-1">
              <Clock className="w-3.5 h-3.5" />
              <span>Submitted: {new Date(vendor.created_at).toLocaleString()}</span>
            </div>
            <div>
              <span>Last Updated: {new Date(vendor.updated_at).toLocaleString()}</span>
            </div>
          </div>
        </div>

        {/* Modal Footer */}
        <div className="border-t border-slate-200 bg-slate-50 px-6 py-3 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 bg-slate-800 hover:bg-slate-900 text-white rounded-lg text-xs font-semibold shadow-sm transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
