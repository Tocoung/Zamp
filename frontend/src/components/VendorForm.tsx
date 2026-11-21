import React, { useState } from 'react';
import {
  Building2,
  User,
  MapPin,
  FileText,
  CreditCard,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Sparkles,
  RotateCcw,
} from 'lucide-react';
import { createVendor, VendorCreatePayload, VendorResponse } from '../config/api';

interface VendorFormProps {
  onVendorCreated?: (vendor: VendorResponse) => void;
  onNavigateToDirectory?: () => void;
}

const INITIAL_FORM_STATE: VendorCreatePayload = {
  legal_name: '',
  trade_name: '',
  business_type: 'Private Limited',
  country_of_incorporation: 'United States',
  registration_number: '',

  contact_name: '',
  contact_email: '',
  contact_phone: '',

  address_line1: '',
  address_line2: '',
  city: '',
  state_province: '',
  postal_code: '',
  address_country: 'United States',

  tax_id_type: 'EIN',
  tax_id_number: '',

  bank_account_holder_name: '',
  bank_name: '',
  bank_account_number: '',
  bank_routing_number: '',
  bank_country: 'United States',
};

const SAMPLE_DEMO_DATA: VendorCreatePayload = {
  legal_name: 'Apex Global Logistics Inc.',
  trade_name: 'Apex Express',
  business_type: 'Private Limited',
  country_of_incorporation: 'United States',
  registration_number: 'US-DEL-2024-91024',

  contact_name: 'Sarah Jenkins',
  contact_email: 'sarah.jenkins@apexgl.com',
  contact_phone: '+1 (555) 392-8172',

  address_line1: '100 Enterprise Way',
  address_line2: 'Suite 450',
  city: 'San Jose',
  state_province: 'California',
  postal_code: '95110',
  address_country: 'United States',

  tax_id_type: 'EIN',
  tax_id_number: '94-3829104',

  bank_account_holder_name: 'Apex Global Logistics Inc.',
  bank_name: 'Silicon Valley Commercial Bank',
  bank_account_number: '8839201948201',
  bank_routing_number: '121000358',
  bank_country: 'United States',
};

export const VendorForm: React.FC<VendorFormProps> = ({
  onVendorCreated,
  onNavigateToDirectory,
}) => {
  const [formData, setFormData] = useState<VendorCreatePayload>(INITIAL_FORM_STATE);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [createdVendor, setCreatedVendor] = useState<VendorResponse | null>(null);

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>
  ) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
    if (error) setError(null);
  };

  const handleFillDemoData = () => {
    setFormData(SAMPLE_DEMO_DATA);
    setCreatedVendor(null);
    setError(null);
  };

  const handleReset = () => {
    setFormData(INITIAL_FORM_STATE);
    setCreatedVendor(null);
    setError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setCreatedVendor(null);

    // Basic client validation
    if (!formData.legal_name.trim()) {
      setError('Legal company name is required');
      return;
    }
    if (!formData.contact_email.trim() || !formData.contact_email.includes('@')) {
      setError('Valid business contact email is required');
      return;
    }
    if (!formData.registration_number.trim()) {
      setError('Company registration number is required');
      return;
    }
    if (!formData.tax_id_number.trim()) {
      setError('Tax ID number is required');
      return;
    }
    if (!formData.bank_account_number.trim() || formData.bank_account_number.length < 4) {
      setError('Bank account number must be at least 4 digits');
      return;
    }

    setIsSubmitting(true);
    try {
      const vendor = await createVendor(formData);
      setCreatedVendor(vendor);
      if (onVendorCreated) {
        onVendorCreated(vendor);
      }
    } catch (err: any) {
      setError(err.message || 'An unexpected error occurred during submission.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
      {/* Header Banner */}
      <div className="border-b border-slate-200 bg-slate-50/70 p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-900 flex items-center gap-2">
            <Building2 className="w-5 h-5 text-sky-600" />
            Vendor Onboarding Registration
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            Submit complete company, tax, and banking details. Every submission starts with <span className="font-semibold text-slate-700">SUBMITTED</span> status.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleFillDemoData}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-sky-50 text-sky-700 border border-sky-200 hover:bg-sky-100 transition-colors"
          >
            <Sparkles className="w-3.5 h-3.5 text-sky-600" />
            Fill Demo Data
          </button>
          <button
            type="button"
            onClick={handleReset}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-100 text-slate-600 border border-slate-200 hover:bg-slate-200 transition-colors"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            Clear
          </button>
        </div>
      </div>

      {/* Success Notification */}
      {createdVendor && (
        <div className="m-6 p-5 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-950 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 animate-in fade-in duration-300">
          <div className="flex items-start gap-3">
            <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
            <div>
              <h4 className="font-semibold text-sm text-emerald-900">
                Vendor Registered Successfully!
              </h4>
              <p className="text-xs text-emerald-800 mt-0.5">
                Record assigned ID: <code className="bg-emerald-100/80 px-1.5 py-0.5 rounded font-mono font-bold text-emerald-900">{createdVendor.id}</code> with initial status <span className="font-bold text-emerald-900">[{createdVendor.status}]</span>.
              </p>
              <p className="text-xs text-emerald-700 mt-1">
                Banking account secured with mask: <span className="font-mono">{createdVendor.bank_account_number_masked}</span>.
              </p>
            </div>
          </div>
          {onNavigateToDirectory && (
            <button
              type="button"
              onClick={onNavigateToDirectory}
              className="px-4 py-2 bg-emerald-700 hover:bg-emerald-800 text-white rounded-lg text-xs font-semibold shadow-sm transition-colors whitespace-nowrap"
            >
              View in Directory →
            </button>
          )}
        </div>
      )}

      {/* Error Notification */}
      {error && (
        <div className="m-6 p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-900 flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
          <div>
            <h4 className="font-semibold text-sm">Submission Error</h4>
            <p className="text-xs text-rose-700 mt-0.5">{error}</p>
          </div>
        </div>
      )}

      {/* Main Form */}
      <form onSubmit={handleSubmit} className="p-6 space-y-8">
        {/* Section 1: Identity & Company Info */}
        <section className="space-y-4">
          <div className="flex items-center gap-2 pb-2 border-b border-slate-100">
            <Building2 className="w-4 h-4 text-sky-600" />
            <h3 className="text-sm font-bold text-slate-800">
              1. Company Identity & Registration
            </h3>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Legal Company Name <span className="text-rose-500">*</span>
              </label>
              <input
                type="text"
                name="legal_name"
                value={formData.legal_name}
                onChange={handleChange}
                required
                placeholder="e.g. Acme Enterprises Inc."
                className="w-full text-xs px-3 py-2 border border-slate-200 rounded-lg focus:ring-2 focus:ring-sky-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Trade Name / DBA <span className="text-slate-400 font-normal">(Optional)</span>
              </label>
              <input
                type="text"
                name="trade_name"
                value={formData.trade_name}
                onChange={handleChange}
                placeholder="e.g. Acme Global"
                className="w-full text-xs px-3 py-2 border border-slate-200 rounded-lg focus:ring-2 focus:ring-sky-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Business Type <span className="text-rose-500">*</span>
              </label>
              <select
                name="business_type"
                value={formData.business_type}
                onChange={handleChange}
                className="w-full text-xs px-3 py-2 border border-slate-200 rounded-lg focus:ring-2 focus:ring-sky-500 focus:outline-none bg-white"
              >
                <option value="Private Limited">Private Limited</option>
                <option value="Public Limited">Public Limited</option>
                <option value="Limited Liability Company (LLC)">Limited Liability Company (LLC)</option>
                <option value="Partnership">Partnership</option>
                <option value="Sole Proprietorship">Sole Proprietorship</option>
                <option value="Other">Other</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Country of Incorporation <span className="text-rose-500">*</span>
              </label>
              <input
                type="text"
                name="country_of_incorporation"
                value={formData.country_of_incorporation}
                onChange={handleChange}
                required
                placeholder="e.g. United States, India, Germany"
                className="w-full text-xs px-3 py-2 border border-slate-200 rounded-lg focus:ring-2 focus:ring-sky-500 focus:outline-none"
              />
            </div>

            <div className="md:col-span-2">
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Company Registration Number <span className="text-rose-500">*</span>
              </label>
              <input
                type="text"
                name="registration_number"
                value={formData.registration_number}
                onChange={handleChange}
                required
                placeholder="e.g. CIN, CRN, or State Filing ID"
                className="w-full text-xs px-3 py-2 border border-slate-200 rounded-lg focus:ring-2 focus:ring-sky-500 focus:outline-none"
              />
            </div>
          </div>
        </section>

        {/* Section 2: Contact Information */}
        <section className="space-y-4">
          <div className="flex items-center gap-2 pb-2 border-b border-slate-100">
            <User className="w-4 h-4 text-sky-600" />
            <h3 className="text-sm font-bold text-slate-800">
              2. Primary Contact Details
            </h3>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Contact Person Full Name <span className="text-rose-500">*</span>
              </label>
              <input
                type="text"
                name="contact_name"
                value={formData.contact_name}
                onChange={handleChange}
                required
                placeholder="e.g. Eleanor Vance"
                className="w-full text-xs px-3 py-2 border border-slate-200 rounded-lg focus:ring-2 focus:ring-sky-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Business Email Address <span className="text-rose-500">*</span>
              </label>
              <input
                type="email"
                name="contact_email"
                value={formData.contact_email}
                onChange={handleChange}
                required
                placeholder="e.g. e.vance@company.com"
                className="w-full text-xs px-3 py-2 border border-slate-200 rounded-lg focus:ring-2 focus:ring-sky-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Contact Phone Number <span className="text-rose-500">*</span>
              </label>
              <input
                type="tel"
                name="contact_phone"
                value={formData.contact_phone}
                onChange={handleChange}
                required
                placeholder="e.g. +1 (555) 019-2834"
                className="w-full text-xs px-3 py-2 border border-slate-200 rounded-lg focus:ring-2 focus:ring-sky-500 focus:outline-none"
              />
            </div>
          </div>
        </section>

        {/* Section 3: Registered Address */}
        <section className="space-y-4">
          <div className="flex items-center gap-2 pb-2 border-b border-slate-100">
            <MapPin className="w-4 h-4 text-sky-600" />
            <h3 className="text-sm font-bold text-slate-800">
              3. Registered Headquarters Address
            </h3>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <div className="md:col-span-2">
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Address Line 1 <span className="text-rose-500">*</span>
              </label>
              <input
                type="text"
                name="address_line1"
                value={formData.address_line1}
                onChange={handleChange}
                required
                placeholder="e.g. 742 Evergreen Terrace"
                className="w-full text-xs px-3 py-2 border border-slate-200 rounded-lg focus:ring-2 focus:ring-sky-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Address Line 2 <span className="text-slate-400 font-normal">(Optional)</span>
              </label>
              <input
                type="text"
                name="address_line2"
                value={formData.address_line2}
                onChange={handleChange}
                placeholder="e.g. Suite 300, Floor 4"
                className="w-full text-xs px-3 py-2 border border-slate-200 rounded-lg focus:ring-2 focus:ring-sky-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                City <span className="text-rose-500">*</span>
              </label>
              <input
                type="text"
                name="city"
                value={formData.city}
                onChange={handleChange}
                required
                placeholder="e.g. Austin"
                className="w-full text-xs px-3 py-2 border border-slate-200 rounded-lg focus:ring-2 focus:ring-sky-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                State / Province / Region <span className="text-rose-500">*</span>
              </label>
              <input
                type="text"
                name="state_province"
                value={formData.state_province}
                onChange={handleChange}
                required
                placeholder="e.g. Texas"
                className="w-full text-xs px-3 py-2 border border-slate-200 rounded-lg focus:ring-2 focus:ring-sky-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Postal / Zip Code <span className="text-rose-500">*</span>
              </label>
              <input
                type="text"
                name="postal_code"
                value={formData.postal_code}
                onChange={handleChange}
                required
                placeholder="e.g. 78701"
                className="w-full text-xs px-3 py-2 border border-slate-200 rounded-lg focus:ring-2 focus:ring-sky-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Address Country <span className="text-rose-500">*</span>
              </label>
              <input
                type="text"
                name="address_country"
                value={formData.address_country}
                onChange={handleChange}
                required
                placeholder="e.g. United States"
                className="w-full text-xs px-3 py-2 border border-slate-200 rounded-lg focus:ring-2 focus:ring-sky-500 focus:outline-none"
              />
            </div>
          </div>
        </section>

        {/* Section 4: Tax Information */}
        <section className="space-y-4">
          <div className="flex items-center gap-2 pb-2 border-b border-slate-100">
            <FileText className="w-4 h-4 text-sky-600" />
            <h3 className="text-sm font-bold text-slate-800">
              4. Tax Registration Details
            </h3>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Tax Identification Type <span className="text-rose-500">*</span>
              </label>
              <select
                name="tax_id_type"
                value={formData.tax_id_type}
                onChange={handleChange}
                className="w-full text-xs px-3 py-2 border border-slate-200 rounded-lg focus:ring-2 focus:ring-sky-500 focus:outline-none bg-white"
              >
                <option value="EIN">US Employer Identification Number (EIN)</option>
                <option value="SSN">US Social Security Number (SSN)</option>
                <option value="VAT">EU / UK Value Added Tax (VAT)</option>
                <option value="GSTIN">India GST Identification Number (GSTIN)</option>
                <option value="PAN">India Permanent Account Number (PAN)</option>
                <option value="CRN">Company Registration Tax ID (Generic)</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Tax Identification Number <span className="text-rose-500">*</span>
              </label>
              <input
                type="text"
                name="tax_id_number"
                value={formData.tax_id_number}
                onChange={handleChange}
                required
                placeholder="e.g. 12-3456789 or 27AAAAA0000A1Z5"
                className="w-full text-xs px-3 py-2 border border-slate-200 rounded-lg focus:ring-2 focus:ring-sky-500 focus:outline-none"
              />
            </div>
          </div>
        </section>

        {/* Section 5: Banking Information */}
        <section className="space-y-4">
          <div className="flex items-center gap-2 pb-2 border-b border-slate-100">
            <CreditCard className="w-4 h-4 text-sky-600" />
            <h3 className="text-sm font-bold text-slate-800">
              5. Banking & Settlement Information
            </h3>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Account Holder Name <span className="text-rose-500">*</span>
              </label>
              <input
                type="text"
                name="bank_account_holder_name"
                value={formData.bank_account_holder_name}
                onChange={handleChange}
                required
                placeholder="Matches legal company name"
                className="w-full text-xs px-3 py-2 border border-slate-200 rounded-lg focus:ring-2 focus:ring-sky-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Bank Name <span className="text-rose-500">*</span>
              </label>
              <input
                type="text"
                name="bank_name"
                value={formData.bank_name}
                onChange={handleChange}
                required
                placeholder="e.g. JPMorgan Chase Bank, N.A."
                className="w-full text-xs px-3 py-2 border border-slate-200 rounded-lg focus:ring-2 focus:ring-sky-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Bank Country <span className="text-rose-500">*</span>
              </label>
              <input
                type="text"
                name="bank_country"
                value={formData.bank_country}
                onChange={handleChange}
                required
                placeholder="e.g. United States"
                className="w-full text-xs px-3 py-2 border border-slate-200 rounded-lg focus:ring-2 focus:ring-sky-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Bank Account Number <span className="text-rose-500">*</span>
              </label>
              <input
                type="text"
                name="bank_account_number"
                value={formData.bank_account_number}
                onChange={handleChange}
                required
                placeholder="e.g. 987654321098"
                className="w-full text-xs px-3 py-2 border border-slate-200 rounded-lg focus:ring-2 focus:ring-sky-500 focus:outline-none font-mono"
              />
              <span className="text-[10px] text-slate-500 mt-1 block">
                Sensitive field: permanently masked on responses and in logs.
              </span>
            </div>

            <div className="md:col-span-2">
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Routing Code (ABA / SWIFT / BIC / IFSC) <span className="text-rose-500">*</span>
              </label>
              <input
                type="text"
                name="bank_routing_number"
                value={formData.bank_routing_number}
                onChange={handleChange}
                required
                placeholder="e.g. 021000021 (ABA) or CHASUS33 (SWIFT)"
                className="w-full text-xs px-3 py-2 border border-slate-200 rounded-lg focus:ring-2 focus:ring-sky-500 focus:outline-none font-mono"
              />
            </div>
          </div>
        </section>

        {/* Submit Actions */}
        <div className="pt-4 border-t border-slate-200 flex items-center justify-end gap-3">
          <button
            type="button"
            onClick={handleReset}
            disabled={isSubmitting}
            className="px-4 py-2 border border-slate-300 rounded-lg text-xs font-medium text-slate-700 hover:bg-slate-50 transition-colors"
          >
            Reset
          </button>
          <button
            type="submit"
            disabled={isSubmitting}
            className="inline-flex items-center gap-2 px-6 py-2 bg-sky-600 hover:bg-sky-700 disabled:bg-sky-400 text-white rounded-lg text-xs font-semibold shadow-sm transition-colors"
          >
            {isSubmitting ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Saving Vendor Record...</span>
              </>
            ) : (
              <span>Submit Vendor Registration</span>
            )}
          </button>
        </div>
      </form>
    </div>
  );
};
