import React, { useState, useEffect } from 'react';
import {
  CheckCircle2,
  AlertTriangle,
  AlertOctagon,
  Info,
  Clock,
  ShieldAlert,
  FileSearch,
  Layers,
  FileText,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  Eye,
  Check,
  X,
  Loader2,
  Filter,
  ShieldCheck,
  AlertCircle,
} from 'lucide-react';
import {
  VerificationRunResponse,
  VerificationRunStatus,
  FindingResult,
  FindingSeverity,
  VerificationRunSummary,
  runVendorVerification,
  fetchLatestVerification,
  fetchVerificationHistory,
  fetchVerificationRun,
  getDocumentPagePreviewUrl,
} from '../config/api';

interface VerificationPanelProps {
  vendorId: string;
  onActivityChange?: () => void;
  onInspectDocumentPage?: (documentId: string, pageNumber: number, fieldName?: string) => void;
}

export const VerificationPanel: React.FC<VerificationPanelProps> = ({
  vendorId,
  onActivityChange,
  onInspectDocumentPage,
}) => {
  const [latestRun, setLatestRun] = useState<VerificationRunResponse | null>(null);
  const [history, setHistory] = useState<VerificationRunSummary[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [resultFilter, setResultFilter] = useState<'ALL' | 'DISCREPANCIES' | 'MATCHES' | 'INCOMPLETE'>('ALL');
  const [severityFilter, setSeverityFilter] = useState<'ALL' | 'CRITICAL' | 'WARNING' | 'INFO'>('ALL');

  // Expanded evidence sections
  const [expandedFindings, setExpandedFindings] = useState<Set<string>>(new Set());

  // Historical run viewing
  const [viewingHistoricalRunId, setViewingHistoricalRunId] = useState<string | null>(null);

  // Embedded Page Preview Modal State
  const [previewDocId, setPreviewDocId] = useState<string | null>(null);
  const [previewPageNum, setPreviewPageNum] = useState<number>(1);
  const [previewFieldName, setPreviewFieldName] = useState<string | null>(null);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  useEffect(() => {
    if (vendorId) {
      loadInitialData();
    }
  }, [vendorId]);

  const loadInitialData = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [latest, hist] = await Promise.all([
        fetchLatestVerification(vendorId),
        fetchVerificationHistory(vendorId, 1, 10).catch(() => ({ total: 0, page: 1, page_size: 10, items: [] })),
      ]);
      setLatestRun(latest);
      setHistory(hist?.items || []);
    } catch (err: any) {
      setError(err.message || 'Failed to load verification status');
    } finally {
      setIsLoading(false);
    }
  };

  const handleRunVerification = async () => {
    setIsRunning(true);
    setError(null);
    try {
      const result = await runVendorVerification(vendorId);
      setLatestRun(result);
      setViewingHistoricalRunId(null);
      // Reload history
      const hist = await fetchVerificationHistory(vendorId, 1, 10).catch(() => ({ total: 0, page: 1, page_size: 10, items: [] }));
      setHistory(hist?.items || []);
      if (onActivityChange) {
        onActivityChange();
      }
    } catch (err: any) {
      setError(err.message || 'Failed to execute cross-document verification');
    } finally {
      setIsRunning(false);
    }
  };

  const handleViewHistoricalRun = async (runId: string) => {
    if (latestRun && latestRun.id === runId && !viewingHistoricalRunId) {
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const run = await fetchVerificationRun(vendorId, runId);
      setLatestRun(run);
      setViewingHistoricalRunId(runId);
    } catch (err: any) {
      setError(err.message || 'Failed to load historical run');
    } finally {
      setIsLoading(false);
    }
  };

  const toggleExpand = (findingId: string) => {
    setExpandedFindings((prev) => {
      const next = new Set(prev);
      if (next.has(findingId)) {
        next.delete(findingId);
      } else {
        next.add(findingId);
      }
      return next;
    });
  };

  const handleOpenPagePreview = (documentId: string, pageNumber: number = 1, fieldName?: string) => {
    if (onInspectDocumentPage) {
      onInspectDocumentPage(documentId, pageNumber, fieldName);
    }
    setPreviewDocId(documentId);
    setPreviewPageNum(pageNumber);
    setPreviewFieldName(fieldName || null);
    setIsPreviewLoading(true);
    setPreviewError(null);
  };

  const getStatusBadge = (status: VerificationRunStatus) => {
    switch (status) {
      case 'COMPLETED':
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
            COMPLETED
          </span>
        );
      case 'COMPLETED_WITH_FINDINGS':
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-sky-50 text-sky-700 border border-sky-200">
            <Info className="w-3.5 h-3.5 text-sky-600" />
            COMPLETED WITH FINDINGS
          </span>
        );
      case 'NEEDS_REVIEW':
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
            <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
            NEEDS REVIEW
          </span>
        );
      case 'INCOMPLETE':
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-orange-50 text-orange-700 border border-orange-200">
            <AlertOctagon className="w-3.5 h-3.5 text-orange-600" />
            INCOMPLETE
          </span>
        );
      case 'FAILED':
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200">
            <AlertCircle className="w-3.5 h-3.5 text-rose-600" />
            FAILED
          </span>
        );
      case 'NOT_RUN':
      default:
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-200">
            <Clock className="w-3.5 h-3.5 text-slate-500" />
            NOT RUN
          </span>
        );
    }
  };

  const getResultBadge = (result: FindingResult) => {
    switch (result) {
      case 'MATCH':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            <Check className="w-3 h-3 text-emerald-600" />
            MATCH
          </span>
        );
      case 'CONFIRMED_DISCREPANCY':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-rose-50 text-rose-700 border border-rose-200">
            <AlertOctagon className="w-3 h-3 text-rose-600" />
            CONFIRMED DISCREPANCY
          </span>
        );
      case 'POTENTIAL_DISCREPANCY':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-amber-50 text-amber-700 border border-amber-200">
            <AlertTriangle className="w-3 h-3 text-amber-600" />
            POTENTIAL DISCREPANCY
          </span>
        );
      case 'INSUFFICIENT_EVIDENCE':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-slate-100 text-slate-700 border border-slate-200">
            <Info className="w-3 h-3 text-slate-500" />
            INSUFFICIENT EVIDENCE
          </span>
        );
      case 'MISSING_DOCUMENT':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-orange-50 text-orange-700 border border-orange-200">
            <FileText className="w-3 h-3 text-orange-600" />
            MISSING DOCUMENT
          </span>
        );
      case 'UNSUPPORTED_DOCUMENT':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-purple-50 text-purple-700 border border-purple-200">
            <Info className="w-3 h-3 text-purple-600" />
            UNSUPPORTED
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] bg-slate-100 text-slate-700">
            {result}
          </span>
        );
    }
  };

  const getSeverityBadge = (severity: FindingSeverity) => {
    switch (severity) {
      case 'CRITICAL':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-rose-600 text-white shadow-xs">
            CRITICAL
          </span>
        );
      case 'WARNING':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-amber-100 text-amber-800 border border-amber-200">
            WARNING
          </span>
        );
      case 'INFO':
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-slate-100 text-slate-600 border border-slate-200">
            INFO
          </span>
        );
    }
  };

  const formatFieldName = (fieldName: string) => {
    return fieldName
      .replace(/_/g, ' ')
      .replace(/\b\w/g, (c) => c.toUpperCase());
  };

  // Filter findings
  const filteredFindings = (latestRun?.findings || []).filter((f) => {
    // Result Filter
    if (resultFilter === 'DISCREPANCIES') {
      if (f.result !== 'CONFIRMED_DISCREPANCY' && f.result !== 'POTENTIAL_DISCREPANCY') return false;
    } else if (resultFilter === 'MATCHES') {
      if (f.result !== 'MATCH') return false;
    } else if (resultFilter === 'INCOMPLETE') {
      if (f.result !== 'MISSING_DOCUMENT' && f.result !== 'INSUFFICIENT_EVIDENCE') return false;
    }

    // Severity Filter
    if (severityFilter !== 'ALL') {
      if (f.severity !== severityFilter) return false;
    }

    return true;
  });

  return (
    <div className="space-y-5">
      {/* Top Header & Actions Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-4 rounded-xl bg-slate-50 border border-slate-200">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-indigo-100 border border-indigo-200 flex items-center justify-center text-indigo-700">
            <FileSearch className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-bold text-slate-900">Cross-Document Verification</h3>
              {latestRun && getStatusBadge(latestRun.status)}
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              {latestRun ? (
                <>
                  Last verified:{' '}
                  <span className="font-semibold text-slate-700">
                    {new Date(latestRun.created_at).toLocaleString()}
                  </span>
                  {viewingHistoricalRunId && (
                    <span className="ml-2 text-indigo-600 font-medium">(Viewing historical run snapshot)</span>
                  )}
                </>
              ) : (
                'Automated statutory reconciliation and discrepancy detection across documents and vendor profile.'
              )}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {viewingHistoricalRunId && (
            <button
              type="button"
              onClick={() => handleViewHistoricalRun(history[0]?.id || '')}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 transition-colors shadow-xs"
            >
              Return to Latest
            </button>
          )}

          <button
            type="button"
            onClick={handleRunVerification}
            disabled={isRunning || isLoading}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-bold bg-indigo-600 hover:bg-indigo-700 text-white shadow-sm transition-colors disabled:opacity-50"
          >
            {isRunning ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Verifying Evidence...</span>
              </>
            ) : (
              <>
                <RefreshCw className="w-4 h-4 text-indigo-200" />
                <span>{latestRun ? 'Re-run Verification' : 'Run Verification'}</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Error Notice */}
      {error && (
        <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center gap-2">
          <ShieldAlert className="w-4 h-4 text-rose-600 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Loading state */}
      {isLoading && !latestRun && (
        <div className="py-12 flex flex-col items-center justify-center gap-3">
          <Loader2 className="w-8 h-8 animate-spin text-indigo-600" />
          <span className="text-xs text-slate-500 font-medium">Loading verification data...</span>
        </div>
      )}

      {/* Not Run / Empty State */}
      {!isLoading && !latestRun && (
        <div className="py-12 px-6 rounded-2xl border-2 border-dashed border-slate-200 text-center space-y-4 bg-slate-50/50">
          <div className="w-12 h-12 rounded-2xl bg-indigo-50 border border-indigo-100 flex items-center justify-center mx-auto text-indigo-600">
            <Layers className="w-6 h-6" />
          </div>
          <div className="max-w-md mx-auto space-y-1">
            <h4 className="text-sm font-bold text-slate-800">No Verification Has Been Run Yet</h4>
            <p className="text-xs text-slate-500">
              Cross-document verification deterministically compares vendor-submitted profile data
              against statutory certificates (GST, Bank Cheque, Certificate of Incorporation) and checks consistency across documents.
            </p>
          </div>
          <button
            type="button"
            onClick={handleRunVerification}
            disabled={isRunning}
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs font-bold bg-indigo-600 hover:bg-indigo-700 text-white shadow-sm transition-colors"
          >
            {isRunning ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <FileSearch className="w-4 h-4 text-indigo-200" />
            )}
            <span>Execute Cross-Document Verification</span>
          </button>
        </div>
      )}

      {/* Run Summary Cards */}
      {latestRun && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <div className="p-3.5 rounded-xl bg-white border border-slate-200 shadow-xs">
              <span className="text-[11px] font-medium text-slate-500 block">Comparisons</span>
              <span className="text-xl font-bold text-slate-800">{latestRun.total_comparisons}</span>
              <span className="text-[10px] text-slate-400 block mt-0.5">Rules evaluated</span>
            </div>

            <div className="p-3.5 rounded-xl bg-emerald-50/70 border border-emerald-200/80 shadow-xs">
              <span className="text-[11px] font-medium text-emerald-700 block">Matches</span>
              <span className="text-xl font-bold text-emerald-800">{latestRun.matches}</span>
              <span className="text-[10px] text-emerald-600 block mt-0.5">Consistent data</span>
            </div>

            <div className={`p-3.5 rounded-xl shadow-xs border ${latestRun.confirmed_discrepancies > 0 ? 'bg-rose-50/90 border-rose-300 ring-1 ring-rose-200' : 'bg-slate-50 border-slate-200'}`}>
              <span className={`text-[11px] font-medium block ${latestRun.confirmed_discrepancies > 0 ? 'text-rose-800 font-bold' : 'text-slate-500'}`}>
                Confirmed Discrepancies
              </span>
              <span className={`text-xl font-bold ${latestRun.confirmed_discrepancies > 0 ? 'text-rose-900' : 'text-slate-700'}`}>
                {latestRun.confirmed_discrepancies}
              </span>
              <span className={`text-[10px] block mt-0.5 ${latestRun.confirmed_discrepancies > 0 ? 'text-rose-700' : 'text-slate-400'}`}>
                {latestRun.confirmed_discrepancies > 0 ? 'Action required' : 'None detected'}
              </span>
            </div>

            <div className={`p-3.5 rounded-xl shadow-xs border ${latestRun.potential_discrepancies > 0 ? 'bg-amber-50/90 border-amber-300 ring-1 ring-amber-200' : 'bg-slate-50 border-slate-200'}`}>
              <span className={`text-[11px] font-medium block ${latestRun.potential_discrepancies > 0 ? 'text-amber-800 font-bold' : 'text-slate-500'}`}>
                Potential Discrepancies
              </span>
              <span className={`text-xl font-bold ${latestRun.potential_discrepancies > 0 ? 'text-amber-900' : 'text-slate-700'}`}>
                {latestRun.potential_discrepancies}
              </span>
              <span className={`text-[10px] block mt-0.5 ${latestRun.potential_discrepancies > 0 ? 'text-amber-700' : 'text-slate-400'}`}>
                Low conf / Ambiguous
              </span>
            </div>

            <div className="p-3.5 rounded-xl bg-orange-50/70 border border-orange-200/80 shadow-xs">
              <span className="text-[11px] font-medium text-orange-700 block">Missing Docs</span>
              <span className="text-xl font-bold text-orange-800">{latestRun.missing_documents}</span>
              <span className="text-[10px] text-orange-600 block mt-0.5">Required for check</span>
            </div>

            <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 shadow-xs">
              <span className="text-[11px] font-medium text-slate-500 block">Incomplete Evid.</span>
              <span className="text-xl font-bold text-slate-800">{latestRun.insufficient_evidence}</span>
              <span className="text-[10px] text-slate-400 block mt-0.5">Unreadable/absent</span>
            </div>
          </div>

          {/* Filter Bar */}
          <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
            <div className="flex items-center gap-2">
              <Filter className="w-3.5 h-3.5 text-slate-400" />
              <span className="text-xs font-semibold text-slate-600">Filters:</span>
              <div className="flex items-center gap-1 bg-slate-100 p-0.5 rounded-lg border border-slate-200 text-xs">
                {(['ALL', 'DISCREPANCIES', 'MATCHES', 'INCOMPLETE'] as const).map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => setResultFilter(mode)}
                    className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-colors ${
                      resultFilter === mode
                        ? 'bg-white text-indigo-700 shadow-xs font-semibold'
                        : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    {mode === 'ALL' ? 'All Findings' : mode === 'DISCREPANCIES' ? 'Discrepancies Only' : mode === 'MATCHES' ? 'Matches' : 'Missing / Incomplete'}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex items-center gap-2 text-xs">
              <span className="text-slate-500 font-medium">Severity:</span>
              <select
                value={severityFilter}
                onChange={(e) => setSeverityFilter(e.target.value as any)}
                className="px-2.5 py-1 rounded-lg border border-slate-200 bg-white text-xs text-slate-700 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              >
                <option value="ALL">All Severities</option>
                <option value="CRITICAL">Critical Only</option>
                <option value="WARNING">Warning Only</option>
                <option value="INFO">Info Only</option>
              </select>
            </div>
          </div>

          {/* Findings List */}
          <div className="space-y-3">
            {filteredFindings.length === 0 ? (
              <div className="p-8 text-center bg-slate-50 rounded-xl border border-slate-200 text-xs text-slate-500">
                No findings match the selected filter criteria.
              </div>
            ) : (
              filteredFindings.map((finding) => {
                const isExpanded = expandedFindings.has(finding.id);
                const isCritical = finding.severity === 'CRITICAL';
                const isConfirmed = finding.result === 'CONFIRMED_DISCREPANCY';
                const isPotential = finding.result === 'POTENTIAL_DISCREPANCY';

                let cardBorder = 'border-slate-200 bg-white';
                if (isCritical) {
                  cardBorder = 'border-rose-300 bg-rose-50/30 ring-1 ring-rose-200';
                } else if (isConfirmed) {
                  cardBorder = 'border-rose-200 bg-white';
                } else if (isPotential) {
                  cardBorder = 'border-amber-200 bg-amber-50/20';
                }

                return (
                  <div
                    key={finding.id}
                    className={`rounded-xl border transition-all shadow-xs ${cardBorder}`}
                  >
                    {/* Finding Header */}
                    <div className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                      <div className="space-y-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-xs font-bold text-slate-900">
                            {formatFieldName(finding.field_name)}
                          </span>
                          <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-slate-100 text-slate-600 border border-slate-200">
                            {finding.comparison_type}
                          </span>
                          {getResultBadge(finding.result)}
                          {getSeverityBadge(finding.severity)}
                          {finding.similarity_score !== null && finding.similarity_score !== undefined && (
                            <span className="text-[11px] font-semibold text-slate-600 px-2 py-0.5 rounded bg-slate-100 border border-slate-200">
                              {Math.round(finding.similarity_score * 100)}% match
                            </span>
                          )}
                        </div>

                        <p className="text-xs text-slate-700 leading-relaxed font-medium">
                          {finding.explanation}
                        </p>

                        {finding.comparison_summary && (
                          <div className="text-[11px] font-mono text-slate-600 bg-slate-50 px-2.5 py-1 rounded border border-slate-200/80 inline-block">
                            {finding.comparison_summary}
                          </div>
                        )}
                      </div>

                      <button
                        type="button"
                        onClick={() => toggleExpand(finding.id)}
                        className="inline-flex items-center gap-1 text-xs font-semibold text-indigo-600 hover:text-indigo-800 transition-colors self-start sm:self-center shrink-0"
                      >
                        <span>{isExpanded ? 'Hide Evidence' : 'Inspect Evidence'}</span>
                        {isExpanded ? (
                          <ChevronUp className="w-4 h-4" />
                        ) : (
                          <ChevronDown className="w-4 h-4" />
                        )}
                      </button>
                    </div>

                    {/* Expandable Traceable Evidence Section */}
                    {isExpanded && (
                      <div className="px-4 pb-4 pt-1 border-t border-slate-100/80 space-y-3 bg-slate-50/50 rounded-b-xl">
                        <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider block">
                          Traceable Evidence Sources ({finding.evidence_sources.length})
                        </span>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                          {finding.evidence_sources.map((src, idx) => (
                            <div
                              key={idx}
                              className="p-3 bg-white rounded-lg border border-slate-200 space-y-2 text-xs shadow-2xs"
                            >
                              <div className="flex items-center justify-between pb-1.5 border-b border-slate-100">
                                <span className="font-semibold text-slate-800 flex items-center gap-1.5">
                                  <span className="w-2 h-2 rounded-full bg-indigo-500" />
                                  Source {idx + 1}: {src.source_type === 'VENDOR_PROFILE' ? 'Vendor Profile' : 'Extracted Document'}
                                </span>
                                {src.extraction_status && (
                                  <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-700">
                                    {src.extraction_status}
                                  </span>
                                )}
                              </div>

                              <div className="space-y-1">
                                <div>
                                  <span className="text-slate-400 block text-[11px]">Compared Value:</span>
                                  <span className="font-mono font-semibold text-slate-900 bg-slate-50 px-2 py-0.5 rounded border border-slate-200 inline-block break-all">
                                    {src.value_display || '—'}
                                  </span>
                                </div>

                                {src.source_type === 'EXTRACTED_DOCUMENT_FIELD' && (
                                  <>
                                    <div className="flex items-center justify-between pt-1 text-[11px] text-slate-600">
                                      <span>Document: <strong className="text-slate-800">{src.document_name || '—'}</strong></span>
                                      {src.page_number && (
                                        <span className="bg-sky-50 text-sky-700 px-1.5 py-0.5 rounded border border-sky-200 font-medium">
                                          Page {src.page_number}
                                        </span>
                                      )}
                                    </div>

                                    {src.confidence_score !== null && src.confidence_score !== undefined && (
                                      <div className="flex items-center justify-between text-[11px] text-slate-500 pt-0.5">
                                        <span>Confidence:</span>
                                        <span className="font-mono font-semibold text-slate-700">
                                          {(src.confidence_score * 100).toFixed(0)}% ({src.extraction_method || 'OCR'})
                                        </span>
                                      </div>
                                    )}

                                    {src.sanitized_snippet && (
                                      <div className="text-[11px] text-slate-500 bg-slate-50 p-1.5 rounded border border-slate-200 font-mono">
                                        Snippet: "{src.sanitized_snippet}"
                                      </div>
                                    )}

                                    {src.document_id && src.page_number && (
                                      <button
                                        type="button"
                                        onClick={() => handleOpenPagePreview(src.document_id!, src.page_number!, finding.field_name)}
                                        className="mt-1 w-full inline-flex items-center justify-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-semibold bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200 transition-colors"
                                      >
                                        <Eye className="w-3.5 h-3.5" />
                                        <span>Inspect Original Page {src.page_number}</span>
                                      </button>
                                    )}
                                  </>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>

          {/* Verification History Section */}
          {history.length > 0 && (
            <div className="space-y-3 pt-4 border-t border-slate-200">
              <h4 className="text-xs font-bold text-slate-600 uppercase tracking-wider flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5 text-slate-400" />
                Previous Verification Executions ({history.length})
              </h4>
              <div className="overflow-x-auto rounded-xl border border-slate-200">
                <table className="w-full text-xs text-left">
                  <thead className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-200">
                    <tr>
                      <th className="px-3.5 py-2">Execution Timestamp</th>
                      <th className="px-3.5 py-2">Status</th>
                      <th className="px-3.5 py-2">Matches</th>
                      <th className="px-3.5 py-2">Confirmed Disc.</th>
                      <th className="px-3.5 py-2">Potential Disc.</th>
                      <th className="px-3.5 py-2">Missing Docs</th>
                      <th className="px-3.5 py-2 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 bg-white">
                    {history.map((item) => (
                      <tr
                        key={item.id}
                        className={`hover:bg-slate-50/70 transition-colors ${
                          latestRun?.id === item.id ? 'bg-indigo-50/40 font-semibold' : ''
                        }`}
                      >
                        <td className="px-3.5 py-2.5 text-slate-800">
                          {new Date(item.created_at).toLocaleString()}
                          {item.id === history[0]?.id && (
                            <span className="ml-1.5 px-1.5 py-0.5 rounded text-[10px] bg-slate-100 text-slate-600 font-mono">
                              latest
                            </span>
                          )}
                        </td>
                        <td className="px-3.5 py-2.5">{getStatusBadge(item.status)}</td>
                        <td className="px-3.5 py-2.5 text-emerald-700 font-medium">{item.matches}</td>
                        <td className="px-3.5 py-2.5">
                          <span className={item.confirmed_discrepancies > 0 ? 'text-rose-600 font-bold' : 'text-slate-500'}>
                            {item.confirmed_discrepancies}
                          </span>
                        </td>
                        <td className="px-3.5 py-2.5">
                          <span className={item.potential_discrepancies > 0 ? 'text-amber-600 font-bold' : 'text-slate-500'}>
                            {item.potential_discrepancies}
                          </span>
                        </td>
                        <td className="px-3.5 py-2.5 text-slate-600">{item.missing_documents}</td>
                        <td className="px-3.5 py-2.5 text-right">
                          <button
                            type="button"
                            onClick={() => handleViewHistoricalRun(item.id)}
                            className="text-xs font-semibold text-indigo-600 hover:text-indigo-800 transition-colors"
                          >
                            {latestRun?.id === item.id && !viewingHistoricalRunId ? 'Current' : 'View Run'}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}

      {/* Compliance / Legal Disclaimer Banner */}
      <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 flex items-start gap-2.5 text-[11px] text-slate-500">
        <ShieldCheck className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
        <div className="leading-relaxed">
          <strong>Compliance & Audit Assurance:</strong> Automated cross-document verification assists human operations and does not constitute a final statutory determination. All bank account numbers are masked across logs, findings, and representations. Discrepancies route vendor submissions to human review (<span className="font-semibold text-amber-700">PENDING</span>) and never trigger automatic rejection.
        </div>
      </div>

      {/* Embedded Original Document Page Preview Modal */}
      {previewDocId && (
        <div className="fixed inset-0 z-60 bg-slate-900/70 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-4xl w-full shadow-2xl border border-slate-200 overflow-hidden animate-in fade-in zoom-in-95 duration-200">
            <div className="border-b border-slate-200 px-5 py-3.5 bg-slate-50 flex items-center justify-between">
              <div>
                <h4 className="text-sm font-bold text-slate-800 flex items-center gap-2">
                  <Eye className="w-4 h-4 text-indigo-600" />
                  Original Document Evidence Preview — Page {previewPageNum}
                </h4>
                {previewFieldName && (
                  <p className="text-xs text-slate-500">
                    Target Field: <span className="font-semibold text-slate-700">{formatFieldName(previewFieldName)}</span>
                  </p>
                )}
              </div>
              <button
                type="button"
                onClick={() => setPreviewDocId(null)}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-200 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6 bg-slate-100 flex items-center justify-center min-h-[460px] max-h-[75vh] overflow-auto relative">
              {isPreviewLoading && (
                <div className="absolute inset-0 bg-white/70 backdrop-blur-xs flex items-center justify-center z-10">
                  <div className="flex flex-col items-center gap-2">
                    <Loader2 className="w-6 h-6 animate-spin text-indigo-600" />
                    <span className="text-xs text-slate-600 font-medium">Rendering document page...</span>
                  </div>
                </div>
              )}

              {previewError ? (
                <div className="p-6 text-center space-y-2">
                  <AlertTriangle className="w-8 h-8 text-amber-500 mx-auto" />
                  <p className="text-xs text-slate-700 font-medium">{previewError}</p>
                </div>
              ) : (
                <img
                  src={getDocumentPagePreviewUrl(vendorId, previewDocId, previewPageNum)}
                  alt={`Document Page ${previewPageNum}`}
                  className="max-h-[650px] w-auto object-contain rounded border border-slate-300 shadow-md select-none bg-white"
                  onLoad={() => setIsPreviewLoading(false)}
                  onError={() => {
                    setIsPreviewLoading(false);
                    setPreviewError('Page preview could not be rendered or page does not exist.');
                  }}
                />
              )}
            </div>

            <div className="border-t border-slate-200 px-5 py-3 bg-slate-50 flex justify-between items-center text-xs text-slate-500">
              <span>Original page image rendered in memory via PDF page renderer.</span>
              <button
                type="button"
                onClick={() => setPreviewDocId(null)}
                className="px-4 py-1.5 bg-slate-800 hover:bg-slate-900 text-white rounded-lg font-semibold transition-colors"
              >
                Close Preview
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};