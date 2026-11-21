import React, { useState, useEffect } from 'react';
import {
  Building2,
  Calendar,
  Globe,
  Mail,
  ChevronLeft,
  ChevronRight,
  Eye,
  RefreshCw,
  Search,
  UserPlus,
  Loader2,
} from 'lucide-react';
import {
  fetchVendors,
  fetchVendorById,
  VendorSummary,
  VendorResponse,
} from '../config/api';
import { VendorDetailModal } from './VendorDetailModal';

interface VendorListProps {
  onNavigateToForm?: () => void;
}

export const VendorList: React.FC<VendorListProps> = ({ onNavigateToForm }) => {
  const [vendors, setVendors] = useState<VendorSummary[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [pageSize] = useState(10);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Search filter
  const [searchTerm, setSearchTerm] = useState('');

  // Selected vendor for modal inspection
  const [selectedVendor, setSelectedVendor] = useState<VendorResponse | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [inspectLoadingId, setInspectLoadingId] = useState<string | null>(null);

  const loadVendors = async (page = 1) => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await fetchVendors(page, pageSize);
      setVendors(data.items);
      setTotalCount(data.total);
      setCurrentPage(data.page);
      setTotalPages(data.total_pages);
    } catch (err: any) {
      setError(err.message || 'Failed to load vendors');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadVendors(currentPage);
  }, [currentPage]);

  const handleInspect = async (vendorId: string) => {
    setInspectLoadingId(vendorId);
    try {
      const fullVendor = await fetchVendorById(vendorId);
      setSelectedVendor(fullVendor);
      setIsModalOpen(true);
    } catch (err: any) {
      alert(`Could not load vendor details: ${err.message}`);
    } finally {
      setInspectLoadingId(null);
    }
  };

  const filteredVendors = vendors.filter((v) => {
    if (!searchTerm.trim()) return true;
    const term = searchTerm.toLowerCase();
    return (
      v.legal_name.toLowerCase().includes(term) ||
      (v.trade_name && v.trade_name.toLowerCase().includes(term)) ||
      v.country_of_incorporation.toLowerCase().includes(term) ||
      v.contact_email.toLowerCase().includes(term) ||
      v.id.toLowerCase().includes(term)
    );
  });

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
      {/* Directory Header */}
      <div className="border-b border-slate-200 bg-slate-50/70 p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-900 flex items-center gap-2">
            <Building2 className="w-5 h-5 text-sky-600" />
            Vendor Records Directory
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            Browse and inspect all submitted vendor entity records. Total registered:{' '}
            <span className="font-semibold text-slate-700">{totalCount}</span>
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => loadVendors(currentPage)}
            disabled={isLoading}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-100 text-slate-600 border border-slate-200 hover:bg-slate-200 transition-colors"
            title="Refresh directory"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
          {onNavigateToForm && (
            <button
              type="button"
              onClick={onNavigateToForm}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-sky-600 text-white hover:bg-sky-700 transition-colors shadow-sm"
            >
              <UserPlus className="w-3.5 h-3.5" />
              Register New
            </button>
          )}
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="p-4 border-b border-slate-100 bg-white flex items-center gap-3">
        <div className="relative flex-1 max-w-md">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search by legal name, trade name, country, or email..."
            className="w-full text-xs pl-9 pr-4 py-2 border border-slate-200 rounded-lg focus:ring-2 focus:ring-sky-500 focus:outline-none"
          />
        </div>
        {searchTerm && (
          <button
            type="button"
            onClick={() => setSearchTerm('')}
            className="text-xs text-slate-400 hover:text-slate-600 underline"
          >
            Clear filter
          </button>
        )}
      </div>

      {/* Error state */}
      {error && (
        <div className="m-6 p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-900 text-xs">
          <strong>Error loading records:</strong> {error}
        </div>
      )}

      {/* Table Content */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="bg-slate-50/80 text-slate-600 font-semibold border-b border-slate-200">
            <tr>
              <th className="py-3.5 px-4">Company Entity</th>
              <th className="py-3.5 px-4">Jurisdiction</th>
              <th className="py-3.5 px-4">Business Type</th>
              <th className="py-3.5 px-4">Contact</th>
              <th className="py-3.5 px-4">Submitted</th>
              <th className="py-3.5 px-4">Status</th>
              <th className="py-3.5 px-4 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {isLoading && vendors.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-12 text-center text-slate-400">
                  <div className="flex flex-col items-center justify-center gap-2">
                    <Loader2 className="w-6 h-6 animate-spin text-sky-600" />
                    <span>Loading vendor records...</span>
                  </div>
                </td>
              </tr>
            ) : filteredVendors.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-12 text-center text-slate-500">
                  <div className="max-w-sm mx-auto flex flex-col items-center justify-center gap-3">
                    <Building2 className="w-10 h-10 text-slate-300" />
                    <div className="font-semibold text-slate-700">No vendor records found</div>
                    <p className="text-xs text-slate-400">
                      {searchTerm
                        ? 'No vendors match your search criteria.'
                        : 'No vendors have been submitted yet. Register your first vendor to begin.'}
                    </p>
                    {onNavigateToForm && !searchTerm && (
                      <button
                        type="button"
                        onClick={onNavigateToForm}
                        className="mt-2 inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-semibold bg-sky-600 text-white hover:bg-sky-700 transition-colors"
                      >
                        <UserPlus className="w-3.5 h-3.5" />
                        Register First Vendor
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ) : (
              filteredVendors.map((vendor) => (
                <tr
                  key={vendor.id}
                  className="hover:bg-slate-50/80 transition-colors group"
                >
                  <td className="py-3.5 px-4">
                    <div className="font-semibold text-slate-900">
                      {vendor.legal_name}
                    </div>
                    {vendor.trade_name && (
                      <div className="text-[11px] text-slate-500">
                        DBA: {vendor.trade_name}
                      </div>
                    )}
                    <div className="text-[10px] font-mono text-slate-400 mt-0.5">
                      {vendor.id.slice(0, 18)}...
                    </div>
                  </td>
                  <td className="py-3.5 px-4 text-slate-700">
                    <div className="flex items-center gap-1.5">
                      <Globe className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                      <span>{vendor.country_of_incorporation}</span>
                    </div>
                  </td>
                  <td className="py-3.5 px-4 text-slate-600">
                    {vendor.business_type}
                  </td>
                  <td className="py-3.5 px-4 text-slate-600">
                    <div className="flex items-center gap-1.5 font-mono text-[11px]">
                      <Mail className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                      <span>{vendor.contact_email}</span>
                    </div>
                  </td>
                  <td className="py-3.5 px-4 text-slate-500 text-[11px]">
                    <div className="flex items-center gap-1.5">
                      <Calendar className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                      <span>{new Date(vendor.created_at).toLocaleDateString()}</span>
                    </div>
                  </td>
                  <td className="py-3.5 px-4">
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-sky-50 text-sky-700 border border-sky-200">
                      {vendor.status}
                    </span>
                  </td>
                  <td className="py-3.5 px-4 text-right">
                    <button
                      type="button"
                      onClick={() => handleInspect(vendor.id)}
                      disabled={inspectLoadingId === vendor.id}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium bg-slate-100 hover:bg-sky-50 text-slate-700 hover:text-sky-700 border border-slate-200 hover:border-sky-200 transition-colors"
                    >
                      {inspectLoadingId === vendor.id ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <Eye className="w-3.5 h-3.5" />
                      )}
                      <span>Inspect</span>
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Footer */}
      <div className="p-4 border-t border-slate-200 bg-slate-50/60 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-slate-600">
        <div>
          Showing page <span className="font-semibold text-slate-900">{currentPage}</span> of{' '}
          <span className="font-semibold text-slate-900">{totalPages}</span> ({totalCount} total vendors)
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
            disabled={currentPage <= 1 || isLoading}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-50 disabled:pointer-events-none transition-colors text-slate-700"
          >
            <ChevronLeft className="w-3.5 h-3.5" />
            Previous
          </button>
          <span className="px-2 font-mono text-[11px]">
            {currentPage} / {totalPages}
          </span>
          <button
            type="button"
            onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
            disabled={currentPage >= totalPages || isLoading}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-50 disabled:pointer-events-none transition-colors text-slate-700"
          >
            Next
            <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Inspect Modal */}
      <VendorDetailModal
        vendor={selectedVendor}
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
      />
    </div>
  );
};
