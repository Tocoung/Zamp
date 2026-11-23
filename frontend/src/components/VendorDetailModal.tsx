import React, { useState, useEffect } from 'react';
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
  Sparkles,
  Edit3,
  Save,
} from 'lucide-react';
import {
  VendorResponse,
  ValidationResult,
  DecisionResult,
  DecisionHistoryItem,
  VendorActivityItem,
  validateExistingVendor,
  runVendorDecision,
  getLatestDecision,
  getDecisionHistory,
  fetchVendorActivities,
  updateVendor,
} from '../config/api';
import { ValidationReport } from './ValidationReport';
import { DecisionReport } from './DecisionReport';
import { VendorActivityTimeline } from './VendorActivityTimeline';
import { DocumentManager } from './DocumentManager';
import { VerificationPanel } from './VerificationPanel';

interface VendorDetailModalProps {
  vendor: VendorResponse | null;
  isOpen: boolean;
  onClose: () => void;
  onVendorUpdated?: (updatedVendor: VendorResponse) => void;
}

export const VendorDetailModal: React.FC<VendorDetailModalProps> = ({
  vendor: initialVendor,
  isOpen,
  onClose,
  onVendorUpdated,
}) => {
  const [vendor, setVendor] = useState<VendorResponse | null>(initialVendor);
  const [copied, setCopied] = useState(false);

  // Validation state
  const [isValidating, setIsValidating] = useState(false);
  const [validationResult, setValidationResult] = useState<ValidationResult | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  // Decision engine state
  const [isEvaluatingDecision, setIsEvaluatingDecision] = useState(false);
  const [decisionResult, setDecisionResult] = useState<DecisionResult | null>(null);
  const [decisionHistory, setDecisionHistory] = useState<DecisionHistoryItem[]>([]);
  const [decisionError, setDecisionError] = useState<string | null>(null);

  // Lifecycle activities state
  const [activities, setActivities] = useState<VendorActivityItem[]>([]);
  const [isLoadingActivities, setIsLoadingActivities] = useState(false);

  // Edit mode state
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<Record<string, any>>({});

  // Sync internal vendor state when prop updates
  useEffect(() => {
    setVendor(initialVendor);
    setValidationResult(null);
    setValidationError(null);
    setDecisionResult(null);
    setDecisionError(null);
    setIsEditing(false);
    setSaveError(null);

    if (initialVendor && isOpen) {
      loadDecisionData(initialVendor.id);
      loadActivities(initialVendor.id);
    }
  }, [initialVendor, isOpen]);

  const loadDecisionData = async (vendorId: string) => {
    try {
      const [latest, historyData] = await Promise.all([
        getLatestDecision(vendorId),
        getDecisionHistory(vendorId, 1, 10).catch(() => ({ items: [] })),
      ]);
      setDecisionResult(latest);
      setDecisionHistory(historyData?.items || []);
    } catch {
      // Ignore initial load failure if vendor has no decision yet
    }
  };

  const loadActivities = async (vendorId: string) => {
    setIsLoadingActivities(true);
    try {
      const data = await fetchVendorActivities(vendorId, 1, 20);
      setActivities(data.items);
    } catch {
      // Ignore initial activity load failure
    } finally {
      setIsLoadingActivities(false);
    }
  };

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

  const handleRunDecision = async () => {
    if (!vendor || isEvaluatingDecision) return;
    setIsEvaluatingDecision(true);
    setDecisionError(null);
    try {
      const decision = await runVendorDecision(vendor.id);
      setDecisionResult(decision);

      // Update local vendor status
      const updated = { ...vendor, status: decision.status };
      setVendor(updated);
      if (onVendorUpdated) {
        onVendorUpdated(updated);
      }

      // Refresh history and activities in parallel
      await Promise.all([
        getDecisionHistory(vendor.id, 1, 10).then((h) => setDecisionHistory(h.items)),
        loadActivities(vendor.id),
      ]);
    } catch (err: any) {
      setDecisionError(err.message || 'Decision calculation failed');
    } finally {
      setIsEvaluatingDecision(false);
    }
  };

  const handleStartEdit = () => {
    setEditForm({
      legal_name: vendor.legal_name || '',
      trade_name: vendor.trade_name || '',
      business_type: vendor.business_type || '',
      country_of_incorporation: vendor.country_of_incorporation || '',
      registration_number: vendor.registration_number || '',
      contact_name: vendor.contact_name || '',
      contact_email: vendor.contact_email || '',
      contact_phone: vendor.contact_phone || '',
      address_line1: vendor.address_line1 || '',
      address_line2: vendor.address_line2 || '',
      city: vendor.city || '',
      state_province: vendor.state_province || '',
      postal_code: vendor.postal_code || '',
      address_country: vendor.address_country || '',
      tax_id_type: vendor.tax_id_type || '',
      tax_id_number: vendor.tax_id_number || '',
      bank_account_holder_name: vendor.bank_account_holder_name || '',
      bank_name: vendor.bank_name || '',
      bank_routing_number: vendor.bank_routing_number || '',
      bank_country: vendor.bank_country || '',
    });
    setSaveError(null);
    setIsEditing(true);
  };

  const handleSaveEdit = async () => {
    if (!vendor || isSaving) return;
    setIsSaving(true);
    setSaveError(null);
    try {
      const updated = await updateVendor(vendor.id, editForm);
      setVendor(updated);
      setIsEditing(false);
      if (onVendorUpdated) {
        onVendorUpdated(updated);
      }
      await loadActivities(vendor.id);
    } catch (err: any) {
      setSaveError(err.message || 'Failed to update vendor record');
    } finally {
      setIsSaving(false);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'APPROVED':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            APPROVED
          </span>
        );
      case 'PENDING':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-amber-50 text-amber-700 border border-amber-200">
            PENDING
          </span>
        );
      case 'REJECTED':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-rose-50 text-rose-700 border border-rose-200">
            REJECTED
          </span>
        );
      case 'SUBMITTED':
      default:
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-sky-50 text-sky-700 border border-sky-200">
            {status}
          </span>
        );
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
                  {vendor.legal_name || 'Unnamed Vendor'}
                </h3>
                {getStatusBadge(vendor.status)}
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
            {/* Edit / Correct Mode Toggle */}
            {!isEditing ? (
              <button
                type="button"
                onClick={handleStartEdit}
                disabled={isEvaluatingDecision || isValidating}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-white hover:bg-slate-100 text-slate-700 border border-slate-200 shadow-xs transition-colors disabled:opacity-50"
              >
                <Edit3 className="w-3.5 h-3.5 text-slate-600" />
                <span>Edit / Correct</span>
              </button>
            ) : (
              <button
                type="button"
                onClick={() => setIsEditing(false)}
                disabled={isSaving}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-100 hover:bg-slate-200 text-slate-700 border border-slate-200 transition-colors"
              >
                <span>Cancel</span>
              </button>
            )}

            {/* Run / Re-evaluate Decision Button */}
            {!isEditing && (
              <button
                type="button"
                onClick={handleRunDecision}
                disabled={isEvaluatingDecision || isValidating}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-700 text-white shadow-xs transition-colors disabled:opacity-50"
              >
                {isEvaluatingDecision ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Evaluating...</span>
                  </>
                ) : (
                  <>
                    <Sparkles className="w-3.5 h-3.5 text-indigo-200" />
                    <span>
                      {decisionResult ? 'Re-evaluate Decision' : 'Run Decision'}
                    </span>
                  </>
                )}
              </button>
            )}

            {/* Validate Button */}
            {!isEditing && (
              <button
                type="button"
                onClick={handleRunValidation}
                disabled={isValidating || isEvaluatingDecision}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-100 hover:bg-slate-200 text-slate-700 border border-slate-200 transition-colors disabled:opacity-50"
              >
                {isValidating ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin text-slate-600" />
                    <span>Validating...</span>
                  </>
                ) : (
                  <>
                    <ShieldCheck className="w-3.5 h-3.5 text-slate-600" />
                    <span>Validate</span>
                  </>
                )}
              </button>
            )}

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
          {/* Decision Error Alert */}
          {decisionError && (
            <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
              <span>{decisionError}</span>
            </div>
          )}

          {/* Validation Request Error */}
          {validationError && (
            <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
              <span>{validationError}</span>
            </div>
          )}

          {/* Save Edit Error Alert */}
          {saveError && (
            <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
              <span>{saveError}</span>
            </div>
          )}

          {/* Decision Engine Result Card */}
          {!isEditing && decisionResult && (
            <DecisionReport
              decision={decisionResult}
              history={decisionHistory}
              onReevaluate={handleRunDecision}
              isEvaluating={isEvaluatingDecision}
            />
          )}

          {/* Validation Report Banner */}
          {!isEditing && validationResult && (
            <ValidationReport
              result={validationResult}
              onClose={() => setValidationResult(null)}
              title="Vendor Record Validation Check"
            />
          )}

          {/* ================= EDIT MODE FORM ================= */}
          {isEditing ? (
            <div className="space-y-4 bg-slate-50 p-4 rounded-xl border border-slate-200">
              <div className="flex items-center justify-between pb-2 border-b border-slate-200">
                <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider flex items-center gap-1.5">
                  <Edit3 className="w-3.5 h-3.5 text-indigo-600" />
                  Correct Vendor Profile Information
                </h4>
                <span className="text-[11px] text-slate-500">
                  Update fields then click Save Changes to re-evaluate
                </span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                <div>
                  <label className="block text-slate-600 font-medium mb-1">Legal Company Name *</label>
                  <input
                    type="text"
                    value={editForm.legal_name || ''}
                    onChange={(e) => setEditForm({ ...editForm, legal_name: e.target.value })}
                    className="w-full px-3 py-1.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-slate-600 font-medium mb-1">Trade Name (Optional)</label>
                  <input
                    type="text"
                    value={editForm.trade_name || ''}
                    onChange={(e) => setEditForm({ ...editForm, trade_name: e.target.value })}
                    className="w-full px-3 py-1.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-slate-600 font-medium mb-1">Company Registration Number *</label>
                  <input
                    type="text"
                    value={editForm.registration_number || ''}
                    onChange={(e) => setEditForm({ ...editForm, registration_number: e.target.value })}
                    className="w-full px-3 py-1.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-1 focus:ring-indigo-500 font-mono"
                  />
                </div>
                <div>
                  <label className="block text-slate-600 font-medium mb-1">Contact Name *</label>
                  <input
                    type="text"
                    value={editForm.contact_name || ''}
                    onChange={(e) => setEditForm({ ...editForm, contact_name: e.target.value })}
                    className="w-full px-3 py-1.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-slate-600 font-medium mb-1">Contact Email *</label>
                  <input
                    type="email"
                    value={editForm.contact_email || ''}
                    onChange={(e) => setEditForm({ ...editForm, contact_email: e.target.value })}
                    className="w-full px-3 py-1.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-1 focus:ring-indigo-500 font-mono"
                  />
                </div>
                <div>
                  <label className="block text-slate-600 font-medium mb-1">Contact Phone *</label>
                  <input
                    type="text"
                    value={editForm.contact_phone || ''}
                    onChange={(e) => setEditForm({ ...editForm, contact_phone: e.target.value })}
                    className="w-full px-3 py-1.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-1 focus:ring-indigo-500 font-mono"
                  />
                </div>
                <div>
                  <label className="block text-slate-600 font-medium mb-1">Tax ID Type *</label>
                  <input
                    type="text"
                    value={editForm.tax_id_type || ''}
                    onChange={(e) => setEditForm({ ...editForm, tax_id_type: e.target.value })}
                    className="w-full px-3 py-1.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-slate-600 font-medium mb-1">Tax Identification Number *</label>
                  <input
                    type="text"
                    value={editForm.tax_id_number || ''}
                    onChange={(e) => setEditForm({ ...editForm, tax_id_number: e.target.value })}
                    className="w-full px-3 py-1.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-1 focus:ring-indigo-500 font-mono"
                  />
                </div>
                <div className="sm:col-span-2">
                  <label className="block text-slate-600 font-medium mb-1">Bank Account Holder Name *</label>
                  <input
                    type="text"
                    value={editForm.bank_account_holder_name || ''}
                    onChange={(e) => setEditForm({ ...editForm, bank_account_holder_name: e.target.value })}
                    className="w-full px-3 py-1.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-slate-600 font-medium mb-1">Bank Name *</label>
                  <input
                    type="text"
                    value={editForm.bank_name || ''}
                    onChange={(e) => setEditForm({ ...editForm, bank_name: e.target.value })}
                    className="w-full px-3 py-1.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-slate-600 font-medium mb-1">Bank Routing Number (IFSC/SWIFT) *</label>
                  <input
                    type="text"
                    value={editForm.bank_routing_number || ''}
                    onChange={(e) => setEditForm({ ...editForm, bank_routing_number: e.target.value })}
                    className="w-full px-3 py-1.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-1 focus:ring-indigo-500 font-mono"
                  />
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-slate-200">
                <button
                  type="button"
                  onClick={() => setIsEditing(false)}
                  disabled={isSaving}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium text-slate-600 hover:bg-slate-200 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleSaveEdit}
                  disabled={isSaving}
                  className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-700 text-white shadow-xs transition-colors disabled:opacity-50"
                >
                  {isSaving ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      <span>Saving...</span>
                    </>
                  ) : (
                    <>
                      <Save className="w-3.5 h-3.5" />
                      <span>Save Changes</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          ) : (
            /* ================= READ-ONLY PROFILE VIEWS ================= */
            <>
              {/* Section 1: Company Identity */}
              <div className="space-y-2">
                <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
                  <Building2 className="w-3.5 h-3.5 text-sky-600" />
                  Company Identity
                </h4>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 p-3.5 rounded-xl bg-slate-50/70 border border-slate-200/80 text-xs">
                  <div>
                    <span className="text-slate-500 block">Legal Name</span>
                    <span className="font-semibold text-slate-800">{vendor.legal_name || '—'}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Trade Name</span>
                    <span className="font-semibold text-slate-800">
                      {vendor.trade_name || '—'}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Business Type</span>
                    <span className="font-semibold text-slate-800">{vendor.business_type || '—'}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Country of Incorporation</span>
                    <span className="font-semibold text-slate-800">{vendor.country_of_incorporation || '—'}</span>
                  </div>
                  <div className="sm:col-span-2">
                    <span className="text-slate-500 block">Registration Number</span>
                    <span className="font-mono font-semibold text-slate-800">
                      {vendor.registration_number || '—'}
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
                    <span className="font-semibold text-slate-800">{vendor.contact_name || '—'}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Business Email</span>
                    <span className="font-mono text-slate-800">{vendor.contact_email || '—'}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Phone Number</span>
                    <span className="font-semibold text-slate-800">{vendor.contact_phone || '—'}</span>
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
                    {vendor.address_line1 || '—'}
                    {vendor.address_line2 ? `, ${vendor.address_line2}` : ''}
                  </div>
                  <div className="text-slate-600">
                    {vendor.city || '—'}, {vendor.state_province || '—'} {vendor.postal_code || '—'}
                  </div>
                  <div className="text-slate-500 font-medium">
                    {vendor.address_country || '—'}
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
                    <span className="font-semibold text-slate-800">{vendor.tax_id_type || '—'}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Tax Identification Number</span>
                    <span className="font-mono font-semibold text-slate-800">
                      {vendor.tax_id_number || '—'}
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
                      {vendor.bank_account_holder_name || '—'}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Bank Name</span>
                    <span className="font-semibold text-slate-800">{vendor.bank_name || '—'}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Bank Country</span>
                    <span className="font-semibold text-slate-800">{vendor.bank_country || '—'}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Account Number</span>
                    <span className="font-mono font-bold text-sky-800 bg-sky-50 px-2 py-0.5 rounded border border-sky-200 inline-block">
                      {vendor.bank_account_number_masked || '••••'}
                    </span>
                  </div>
                  <div className="sm:col-span-2">
                    <span className="text-slate-500 block">Routing / SWIFT / IFSC Code</span>
                    <span className="font-mono font-semibold text-slate-800">
                      {vendor.bank_routing_number || '—'}
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

              {/* Section 6: Supporting Documents Intake */}
              <div className="pt-2 border-t border-slate-200">
                <DocumentManager
                  vendorId={vendor.id}
                  onActivityChange={() => loadActivities(vendor.id)}
                />
              </div>

              {/* Section 7: Cross-Document Validation & Discrepancy Detection */}
              <div className="pt-2 border-t border-slate-200">
                <VerificationPanel
                  vendorId={vendor.id}
                  onActivityChange={() => {
                    loadActivities(vendor.id);
                    if (initialVendor) {
                      loadDecisionData(initialVendor.id);
                    }
                  }}
                />
              </div>

              {/* Section 8: Lifecycle Activity History */}
              <div className="pt-2 border-t border-slate-200">
                <VendorActivityTimeline activities={activities} isLoading={isLoadingActivities} />
              </div>

              {/* Section 8: Metadata */}
              <div className="pt-2 border-t border-slate-100 flex flex-wrap items-center justify-between gap-3 text-[11px] text-slate-400">
                <div className="flex items-center gap-1">
                  <Clock className="w-3.5 h-3.5" />
                  <span>Submitted: {new Date(vendor.created_at).toLocaleString()}</span>
                </div>
                <div>
                  <span>Last Updated: {new Date(vendor.updated_at).toLocaleString()}</span>
                </div>
              </div>
            </>
          )}
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
