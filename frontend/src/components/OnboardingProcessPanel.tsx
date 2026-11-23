import React, { useState, useEffect } from 'react';
import {
  Sparkles,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Clock,
  RotateCw,
  FileText,
  ChevronDown,
  ChevronUp,
  ShieldCheck,
  AlertCircle,
  Layers,
  History,
  ArrowLeft,
} from 'lucide-react';
import {
  OnboardingProcessRunResponse,
  DocumentProcessItem,
  fetchOnboardingProcessHistory,
} from '../config/api';

interface OnboardingProcessPanelProps {
  vendorId?: string;
  run: OnboardingProcessRunResponse | null;
  isProcessing: boolean;
  onProcess: (forceReprocess: boolean) => void;
  error?: string | null;
}

const STAGES = [
  { key: '1_registration', label: '1. Registration' },
  { key: '2_document_intake', label: '2. Intake' },
  { key: '3_classification', label: '3. Classification' },
  { key: '4_ocr_extraction', label: '4. OCR Recognition' },
  { key: '5_structured_extraction', label: '5. Structured Extraction' },
  { key: '6_evidence_assessment', label: '6. Evidence Assessment' },
  { key: '7_cross_verification', label: '7. Verification' },
  { key: '8_decision', label: '8. Final Decision' },
];

export const OnboardingProcessPanel: React.FC<OnboardingProcessPanelProps> = ({
  vendorId,
  run,
  isProcessing,
  onProcess,
  error,
}) => {
  const [showDocDetails, setShowDocDetails] = useState(true);
  const [showHistory, setShowHistory] = useState(false);
  const [historyRuns, setHistoryRuns] = useState<OnboardingProcessRunResponse[]>([]);
  const [selectedHistoricalRun, setSelectedHistoricalRun] = useState<OnboardingProcessRunResponse | null>(null);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);

  // Load execution history whenever vendorId or latest run changes
  useEffect(() => {
    if (vendorId) {
      loadHistory(vendorId);
    }
  }, [vendorId, run?.id]);

  const loadHistory = async (vid: string) => {
    setIsLoadingHistory(true);
    setHistoryError(null);
    try {
      const resp = await fetchOnboardingProcessHistory(vid);
      setHistoryRuns(resp.runs || []);
    } catch {
      setHistoryError('Could not retrieve processing history.');
    } finally {
      setIsLoadingHistory(false);
    }
  };

  // Active view run: selected historical run if chosen, else latest run
  const activeRun = selectedHistoricalRun || run;
  const isViewingHistorical = selectedHistoricalRun !== null && run !== null && selectedHistoricalRun.id !== run.id;

  if (!activeRun && !isProcessing && !error) {
    return (
      <div className="p-4 rounded-xl border border-indigo-100 bg-gradient-to-r from-indigo-50/70 via-sky-50/50 to-white text-xs">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-start gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-indigo-600 text-white flex items-center justify-center shrink-0 shadow-xs">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <h4 className="font-semibold text-slate-800 text-sm">
                End-to-End Onboarding Pipeline
              </h4>
              <p className="text-slate-500 mt-0.5 text-xs">
                Run automated classification, OCR extraction, cross-document verification, and evidence-aware decisioning.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => onProcess(false)}
            disabled={isProcessing}
            className="inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-700 text-white shadow-xs transition-colors shrink-0"
          >
            <Sparkles className="w-3.5 h-3.5 text-indigo-200" />
            <span>Process Onboarding</span>
          </button>
        </div>
      </div>
    );
  }

  const decisionStatus = activeRun?.decision_status;
  const isApproved = decisionStatus === 'APPROVED';
  const isPending = decisionStatus === 'PENDING';

  return (
    <div className="space-y-4 rounded-xl border border-slate-200 bg-white p-4 text-xs shadow-xs">
      {/* Historical Run Banner Indicator */}
      {isViewingHistorical && activeRun && (
        <div className="p-2.5 rounded-lg bg-amber-50 border border-amber-300 text-amber-900 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Clock className="w-4 h-4 text-amber-700 shrink-0" />
            <span>
              <strong>Viewing Historical Run</strong> (Executed: {new Date(activeRun.created_at).toLocaleString()}) — Read-only execution snapshot.
            </span>
          </div>
          <button
            type="button"
            onClick={() => setSelectedHistoricalRun(null)}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-white border border-amber-300 text-amber-900 font-semibold text-[11px] hover:bg-amber-100 transition-colors shrink-0"
          >
            <ArrowLeft className="w-3 h-3" />
            <span>Back to Latest Run</span>
          </button>
        </div>
      )}

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b border-slate-200">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-indigo-100 text-indigo-700 flex items-center justify-center shrink-0">
            <Layers className="w-4 h-4" />
          </div>
          <div>
            <h4 className="font-bold text-slate-800 text-sm flex items-center gap-2">
              Automated Onboarding Workflow
              {activeRun && (
                <span
                  className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border ${
                    activeRun.status === 'COMPLETED'
                      ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                      : activeRun.status === 'PARTIAL_FAILURE'
                      ? 'bg-amber-50 text-amber-700 border-amber-200'
                      : 'bg-rose-50 text-rose-700 border-rose-200'
                  }`}
                >
                  {activeRun.status.replace('_', ' ')}
                </span>
              )}
            </h4>
            {activeRun && (
              <span className="text-[11px] text-slate-400">
                Trigger: {activeRun.trigger_source} • Executed: {new Date(activeRun.created_at).toLocaleTimeString()}
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => onProcess(true)}
            disabled={isProcessing}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-100 hover:bg-slate-200 text-slate-700 border border-slate-200 transition-colors disabled:opacity-50"
          >
            <RotateCw className={`w-3.5 h-3.5 ${isProcessing ? 'animate-spin text-indigo-600' : 'text-slate-500'}`} />
            <span>{isProcessing ? 'Processing...' : 'Reprocess Workflow'}</span>
          </button>
        </div>
      </div>

      {/* Error alert */}
      {error && (
        <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-800 flex items-center gap-2">
          <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Decision Status Banner */}
      {activeRun && decisionStatus && (
        <div
          className={`p-3.5 rounded-xl border flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
            isApproved
              ? 'bg-emerald-50/80 border-emerald-200 text-emerald-900'
              : isPending
              ? 'bg-amber-50/80 border-amber-200 text-amber-900'
              : 'bg-rose-50/80 border-rose-200 text-rose-900'
          }`}
        >
          <div className="flex items-start gap-2.5">
            {isApproved ? (
              <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
            ) : isPending ? (
              <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
            ) : (
              <XCircle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
            )}
            <div>
              <div className="font-bold text-sm flex items-center gap-2">
                Onboarding Decision: {decisionStatus}
                <span className="text-[11px] font-normal px-2 py-0.5 rounded-full bg-white/60 border border-current">
                  {isApproved
                    ? 'All Evidence Verified'
                    : isPending
                    ? 'Human Review Required'
                    : 'Statutory Syntax Blocking'}
                </span>
              </div>
              <p className="text-xs mt-1 text-slate-700">
                {isApproved
                  ? 'All mandatory vendor profile fields and statutory documents have been matched and verified with high confidence.'
                  : isPending
                  ? 'Vendor requires manual verification due to missing documents, low-confidence OCR, or cross-document discrepancies.'
                  : 'Vendor profile violates statutory registration format requirements or contains dummy account values.'}
              </p>
              {activeRun.decision_reasons && activeRun.decision_reasons.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {activeRun.decision_reasons.map((r, i) => (
                    <span
                      key={i}
                      className="text-[10px] font-mono px-2 py-0.5 rounded bg-white/80 border border-slate-300 text-slate-700"
                    >
                      {r}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 8-Stage Progress Tracker */}
      <div className="space-y-1.5">
        <h5 className="font-semibold text-slate-700 text-xs uppercase tracking-wider flex items-center gap-1.5">
          <ShieldCheck className="w-3.5 h-3.5 text-indigo-600" />
          Pipeline Stages Progress
        </h5>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {STAGES.map((s) => {
            const stageData = activeRun?.stage_results?.[s.key];
            const isCompleted = stageData?.status === 'COMPLETED';
            const isPartial = stageData?.status === 'PARTIAL';
            const isFailed = stageData?.status === 'FAILED';

            return (
              <div
                key={s.key}
                className={`p-2.5 rounded-lg border text-[11px] flex items-center justify-between gap-1.5 ${
                  isCompleted
                    ? 'bg-emerald-50/60 border-emerald-200 text-emerald-800'
                    : isPartial
                    ? 'bg-amber-50/60 border-amber-200 text-amber-800'
                    : isFailed
                    ? 'bg-rose-50/60 border-rose-200 text-rose-800'
                    : 'bg-slate-50 border-slate-200 text-slate-500'
                }`}
              >
                <span className="font-medium truncate">{s.label}</span>
                {isCompleted ? (
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                ) : isPartial ? (
                  <AlertTriangle className="w-3.5 h-3.5 text-amber-600 shrink-0" />
                ) : isFailed ? (
                  <XCircle className="w-3.5 h-3.5 text-rose-600 shrink-0" />
                ) : (
                  <Clock className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Document Processing Breakdown */}
      {activeRun && activeRun.document_breakdown && activeRun.document_breakdown.length > 0 && (
        <div className="space-y-2 pt-2 border-t border-slate-200">
          <div className="flex items-center justify-between">
            <h5 className="font-semibold text-slate-700 text-xs uppercase tracking-wider flex items-center gap-1.5">
              <FileText className="w-3.5 h-3.5 text-indigo-600" />
              Document-Level Processing Breakdown ({activeRun.document_breakdown.length})
            </h5>
            <button
              type="button"
              onClick={() => setShowDocDetails(!showDocDetails)}
              className="text-[11px] text-indigo-600 hover:text-indigo-800 flex items-center gap-1"
            >
              <span>{showDocDetails ? 'Collapse' : 'Expand'}</span>
              {showDocDetails ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            </button>
          </div>

          {showDocDetails && (
            <div className="space-y-2">
              {activeRun.document_breakdown.map((doc: DocumentProcessItem) => (
                <div
                  key={doc.document_id}
                  className={`p-3 rounded-lg border text-xs space-y-1.5 ${
                    doc.eligible_for_verification
                      ? 'bg-slate-50/70 border-slate-200'
                      : 'bg-rose-50/40 border-rose-200'
                  }`}
                >
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1.5">
                    <div className="flex items-center gap-2">
                      <FileText className="w-4 h-4 text-slate-500 shrink-0" />
                      <span className="font-semibold text-slate-800">{doc.file_name}</span>
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-200 text-slate-700">
                        {doc.category || doc.declared_category || 'UNKNOWN'}
                      </span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span
                        className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                          doc.classification_status === 'CLASSIFIED'
                            ? 'bg-emerald-100 text-emerald-800'
                            : 'bg-amber-100 text-amber-800'
                        }`}
                      >
                        {doc.classification_status}
                        {doc.classification_confidence != null &&
                          ` (${Math.round(doc.classification_confidence * 100)}%)`}
                      </span>
                      <span
                        className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                          doc.extraction_status === 'SUCCESS' || doc.extraction_status === 'COMPLETED'
                            ? 'bg-sky-100 text-sky-800'
                            : doc.extraction_status === 'INSUFFICIENT_TEXT'
                            ? 'bg-amber-100 text-amber-800'
                            : 'bg-rose-100 text-rose-800'
                        }`}
                      >
                        OCR: {doc.extraction_status}
                      </span>
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-500">
                    <span>
                      Declared: <strong className="text-slate-700">{doc.declared_category || doc.category || 'N/A'}</strong>
                    </span>
                    <span>
                      Predicted: <strong className="text-slate-700">{doc.predicted_category || 'N/A'}</strong>
                    </span>
                    <span>
                      Extracted Fields: <strong className="text-slate-700">{doc.extracted_fields_count}</strong>
                    </span>
                    {doc.average_confidence != null && (
                      <span>
                        Avg Confidence: <strong className="text-slate-700">{Math.round(doc.average_confidence * 100)}%</strong>
                      </span>
                    )}
                    <span>
                      Verification Eligible:{' '}
                      <strong className={doc.eligible_for_verification ? 'text-emerald-700' : 'text-rose-700'}>
                        {doc.eligible_for_verification ? 'Yes' : 'No'}
                      </strong>
                    </span>
                  </div>

                  {doc.error && (
                    <div className="text-[11px] text-rose-700 bg-rose-50 px-2 py-1 rounded border border-rose-200 flex items-center gap-1.5">
                      <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                      <span>{doc.error}</span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Processing History Section (Section 5) */}
      <div className="pt-2 border-t border-slate-200 space-y-2">
        <div className="flex items-center justify-between">
          <h5 className="font-semibold text-slate-700 text-xs uppercase tracking-wider flex items-center gap-1.5">
            <History className="w-3.5 h-3.5 text-indigo-600" />
            Execution History ({historyRuns.length} runs)
          </h5>
          <button
            type="button"
            onClick={() => setShowHistory(!showHistory)}
            className="text-[11px] text-indigo-600 hover:text-indigo-800 flex items-center gap-1"
          >
            <span>{showHistory ? 'Hide History' : 'Show History'}</span>
            {showHistory ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          </button>
        </div>

        {showHistory && (
          <div className="space-y-2">
            {isLoadingHistory && (
              <div className="p-3 text-center text-slate-400 text-xs flex items-center justify-center gap-2">
                <RotateCw className="w-3.5 h-3.5 animate-spin" />
                <span>Loading execution history...</span>
              </div>
            )}

            {historyError && (
              <div className="p-2.5 rounded bg-rose-50 border border-rose-200 text-rose-700 text-xs">
                {historyError}
              </div>
            )}

            {!isLoadingHistory && historyRuns.length === 0 && (
              <div className="p-3 text-center text-slate-400 text-xs">
                No previous processing runs recorded for this vendor.
              </div>
            )}

            {!isLoadingHistory && historyRuns.length > 0 && (
              <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
                {historyRuns.map((hRun) => {
                  const isCurrentSelected = activeRun?.id === hRun.id;
                  const isLatest = run?.id === hRun.id;
                  return (
                    <div
                      key={hRun.id}
                      className={`p-2.5 rounded-lg border text-xs flex flex-col sm:flex-row sm:items-center justify-between gap-2 transition-colors ${
                        isCurrentSelected
                          ? 'bg-indigo-50/70 border-indigo-300'
                          : 'bg-slate-50/60 border-slate-200 hover:bg-slate-100/70'
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <Clock className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                        <div>
                          <div className="font-semibold text-slate-800 flex items-center gap-1.5">
                            <span>{new Date(hRun.created_at).toLocaleString()}</span>
                            {isLatest && (
                              <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-indigo-100 text-indigo-700">
                                Latest
                              </span>
                            )}
                          </div>
                          <span className="text-[10px] text-slate-500">
                            Trigger: {hRun.trigger_source} • {hRun.successful_documents}/{hRun.total_documents} docs
                          </span>
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        <span
                          className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${
                            hRun.status === 'COMPLETED'
                              ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                              : hRun.status === 'PARTIAL_FAILURE'
                              ? 'bg-amber-50 text-amber-700 border-amber-200'
                              : 'bg-rose-50 text-rose-700 border-rose-200'
                          }`}
                        >
                          {hRun.status.replace('_', ' ')}
                        </span>

                        {hRun.decision_status && (
                          <span
                            className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                              hRun.decision_status === 'APPROVED'
                                ? 'bg-emerald-100 text-emerald-800'
                                : hRun.decision_status === 'PENDING'
                                ? 'bg-amber-100 text-amber-800'
                                : 'bg-rose-100 text-rose-800'
                            }`}
                          >
                            {hRun.decision_status}
                          </span>
                        )}

                        <button
                          type="button"
                          onClick={() => {
                            if (isLatest) {
                              setSelectedHistoricalRun(null);
                            } else {
                              setSelectedHistoricalRun(hRun);
                            }
                          }}
                          disabled={isCurrentSelected}
                          className={`px-2.5 py-1 rounded text-[11px] font-semibold transition-colors ${
                            isCurrentSelected
                              ? 'bg-indigo-600 text-white cursor-default'
                              : 'bg-white border border-slate-300 text-slate-700 hover:bg-slate-50'
                          }`}
                        >
                          {isCurrentSelected ? 'Viewing' : 'Inspect'}
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
