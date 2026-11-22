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
  Filter,
  CheckCircle2,
  Clock,
  XCircle,
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

  // Status and search filters
  const [statusFilter, setStatusFilter] = useState<'ALL' | 'SUBMITTED' | 'APPROVED' | 'PENDING' | 'REJECTED'>('ALL');
  const [searchTerm, setSearchTerm] = useState('');

  // Selected vendor for modal inspection
  const [selectedVendor, setSelectedVendor] = useState<VendorResponse | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [inspectLoadingId, setInspectLoadingId] = useState<string | null>(null);

  // Operational summary counts
  const [metrics, setMetrics] = useState({
    total: 0,
    approved: 0,
    pending: 0,
    rejected: 0,
  });

  const loadMetrics = async () => {
    try {
      const [allRes, appRes, pendRes, rejRes] = await Promise.all([
        fetchVendors(1, 1, 'ALL'),
        fetchVendors(1, 1, 'APPROVED'),
        fetchVendors(1, 1, 'PENDING'),
        fetchVendors(1, 1, 'REJECTED'),
      ]);
      setMetrics({
        total: allRes.total,
        approved: appRes.total,
        pending: pendRes.total,
        rejected: rejRes.total,
      });
    } catch {
      // Graceful fallback
    }
  };

  const loadVendors = async (page = 1, status = statusFilter, search = searchTerm) => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await fetchVendors(page, pageSize, status, search);
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
    loadVendors(currentPage, statusFilter, searchTerm);
    loadMetrics();
  }, [currentPage, statusFilter]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setCurrentPage(1);
    loadVendors(1, statusFilter, searchTerm);
  };

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

  const renderStatusBadge = (status: string) => {
    switch (status) {
      case 'APPROVED':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            APPROVED
          </span>
        );
      case 'PENDING':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-amber-50 text-amber-700 border border-amber-200">
            PENDING
          </span>
        );
      case 'REJECTED':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-rose-50 text-rose-700 border border-rose-200">
            REJECTED
          </span>
        );
      case 'SUBMITTED':
      default:
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-sky-50 text-sky-700 border border-sky-200">
            {status}
          </span>
        );
    }
  };

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
            onClick={() => loadVendors(currentPage, statusFilter, searchTerm)}
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

      {/* Operational Summary Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 p-5 border-b border-slate-200/80 bg-slate-50/40">
        <div
          onClick={() => { setStatusFilter('ALL'); setCurrentPage(1); }}
          className={`cursor-pointer p-4 rounded-xl border transition-all ${
            statusFilter === 'ALL'
              ? 'bg-white border-sky-400 ring-2 ring-sky-100 shadow-sm'
              : 'bg-white border-slate-200/80 hover:border-slate-300'
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-500">Total Entities</span>
            <Building2 className="w-4 h-4 text-slate-400" />
          </div>
          <div className="mt-2 text-2xl font-bold text-slate-900">{metrics.total}</div>
          <div className="text-[11px] text-slate-400 mt-0.5">All registered records</div>
        </div>

        <div
          onClick={() => { setStatusFilter('APPROVED'); setCurrentPage(1); }}
          className={`cursor-pointer p-4 rounded-xl border transition-all ${
            statusFilter === 'APPROVED'
              ? 'bg-white border-emerald-400 ring-2 ring-emerald-100 shadow-sm'
              : 'bg-white border-slate-200/80 hover:border-emerald-300'
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-emerald-700">Approved</span>
            <CheckCircle2 className="w-4 h-4 text-emerald-500" />
          </div>
          <div className="mt-2 text-2xl font-bold text-emerald-900">{metrics.approved}</div>
          <div className="text-[11px] text-emerald-600 mt-0.5">Verified & active vendors</div>
        </div>

        <div
          onClick={() => { setStatusFilter('PENDING'); setCurrentPage(1); }}
          className={`cursor-pointer p-4 rounded-xl border transition-all ${
            statusFilter === 'PENDING'
              ? 'bg-white border-amber-400 ring-2 ring-amber-100 shadow-sm'
              : 'bg-white border-slate-200/80 hover:border-amber-300'
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-amber-700">Pending Review</span>
            <Clock className="w-4 h-4 text-amber-500" />
          </div>
          <div className="mt-2 text-2xl font-bold text-amber-900">{metrics.pending}</div>
          <div className="text-[11px] text-amber-600 mt-0.5">Awaiting compliance review</div>
        </div>

        <div
          onClick={() => { setStatusFilter('REJECTED'); setCurrentPage(1); }}
          className={`cursor-pointer p-4 rounded-xl border transition-all ${
            statusFilter === 'REJECTED'
              ? 'bg-white border-rose-400 ring-2 ring-rose-100 shadow-sm'
              : 'bg-white border-slate-200/80 hover:border-rose-300'
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-rose-700">Rejected</span>
            <XCircle className="w-4 h-4 text-rose-500" />
          </div>
          <div className="mt-2 text-2xl font-bold text-rose-900">{metrics.rejected}</div>
          <div className="text-[11px] text-rose-600 mt-0.5">Failed statutory rules</div>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="p-4 border-b border-slate-100 bg-white flex flex-col md:flex-row md:items-center justify-between gap-3">
        <form onSubmit={handleSearchSubmit} className="relative flex-1 max-w-md">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search by legal name, trade name, country, or email..."
            className="w-full text-xs pl-9 pr-4 py-2 border border-slate-200 rounded-lg focus:ring-2 focus:ring-sky-500 focus:outline-none"
          />
        </form>

        {/* Status Filter Tabs */}
        <div className="flex items-center gap-1.5 overflow-x-auto text-xs">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1 mr-1">
            <Filter className="w-3 h-3" />
            Status:
          </span>
          {(['ALL', 'SUBMITTED', 'APPROVED', 'PENDING', 'REJECTED'] as const).map((st) => (
            <button
              key={st}
              type="button"
              onClick={() => {
                setStatusFilter(st);
                setCurrentPage(1);
              }}
              className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-colors ${
                statusFilter === st
                  ? 'bg-slate-900 text-white shadow-xs'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              {st === 'ALL' ? 'All' : st}
            </button>
          ))}
        </div>
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
            ) : vendors.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-12 text-center text-slate-500">
                  <div className="max-w-sm mx-auto flex flex-col items-center justify-center gap-3">
                    <Building2 className="w-10 h-10 text-slate-300" />
                    <div className="font-semibold text-slate-700">No vendor records found</div>
                    <p className="text-xs text-slate-400">
                      {searchTerm || statusFilter !== 'ALL'
                        ? 'No vendors match your search or filter criteria.'
                        : 'No vendors have been submitted yet. Register your first vendor to begin.'}
                    </p>
                    {onNavigateToForm && !searchTerm && statusFilter === 'ALL' && (
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
              vendors.map((vendor) => (
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
                    {renderStatusBadge(vendor.status)}
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
        onVendorUpdated={(updatedVendor) => {
          setVendors((prev) =>
            prev.map((v) =>
              v.id === updatedVendor.id ? { ...v, status: updatedVendor.status } : v
            )
          );
          loadMetrics();
        }}
      />
    </div>
  );
};
