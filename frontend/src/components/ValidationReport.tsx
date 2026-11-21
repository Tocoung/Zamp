import React, { useState } from 'react';
import {
  CheckCircle2,
  AlertTriangle,
  AlertCircle,
  Info,
  ShieldCheck,
  ChevronRight,
  Filter,
} from 'lucide-react';
import { ValidationResult, ValidationFinding } from '../config/api';

interface ValidationReportProps {
  result: ValidationResult;
  onClose?: () => void;
  title?: string;
}

export const ValidationReport: React.FC<ValidationReportProps> = ({
  result,
  onClose,
  title = 'Deterministic Validation Report',
}) => {
  const [filterSeverity, setFilterSeverity] = useState<'ALL' | 'ERROR' | 'WARNING' | 'INFO'>('ALL');

  const filteredFindings = result.findings.filter((f) => {
    if (filterSeverity === 'ALL') return true;
    return f.severity === filterSeverity;
  });

  const getStatusBadge = () => {
    switch (result.status) {
      case 'PASSED':
        return (
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 text-xs font-semibold">
            <CheckCircle2 className="w-4 h-4 text-emerald-600" />
            <span>Passed (All Checks Succeeded)</span>
          </div>
        );
      case 'PASSED_WITH_WARNINGS':
        return (
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200 text-xs font-semibold">
            <AlertTriangle className="w-4 h-4 text-amber-600" />
            <span>Passed with Warnings</span>
          </div>
        );
      case 'FAILED':
      default:
        return (
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-rose-50 text-rose-700 border border-rose-200 text-xs font-semibold">
            <AlertCircle className="w-4 h-4 text-rose-600" />
            <span>Validation Failed</span>
          </div>
        );
    }
  };

  return (
    <div className="bg-slate-50 border border-slate-200 rounded-xl p-5 space-y-4">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-200 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-indigo-600" />
            <h3 className="font-bold text-slate-900 text-base">{title}</h3>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            Ruleset v{result.ruleset_version} &bull; Validated {new Date(result.validated_at).toLocaleTimeString()} UTC
          </p>
        </div>

        <div className="flex items-center gap-2">
          {getStatusBadge()}
          {onClose && (
            <button
              onClick={onClose}
              className="text-xs text-slate-400 hover:text-slate-600 p-1 rounded"
              title="Close report"
            >
              &times;
            </button>
          )}
        </div>
      </div>

      {/* Summary Metrics Bar */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="bg-white p-3 rounded-lg border border-slate-200 text-center">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 block">
            Checks Run
          </span>
          <span className="text-lg font-bold text-slate-800">{result.summary.total_checks}</span>
        </div>

        <div className="bg-white p-3 rounded-lg border border-slate-200 text-center">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-emerald-600 block">
            Passed Rules
          </span>
          <span className="text-lg font-bold text-emerald-700">{result.summary.passed}</span>
        </div>

        <div className="bg-white p-3 rounded-lg border border-slate-200 text-center">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-rose-600 block">
            Errors
          </span>
          <span className="text-lg font-bold text-rose-700">{result.summary.failed}</span>
        </div>

        <div className="bg-white p-3 rounded-lg border border-slate-200 text-center">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-amber-600 block">
            Warnings
          </span>
          <span className="text-lg font-bold text-amber-700">{result.summary.warnings}</span>
        </div>
      </div>

      {/* Findings Section */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider flex items-center gap-1.5">
            <Filter className="w-3.5 h-3.5 text-slate-400" />
            Field Findings ({filteredFindings.length})
          </h4>

          {/* Severity Filters */}
          <div className="flex items-center gap-1 text-[11px]">
            {(['ALL', 'ERROR', 'WARNING', 'INFO'] as const).map((sev) => (
              <button
                key={sev}
                type="button"
                onClick={() => setFilterSeverity(sev)}
                className={`px-2 py-0.5 rounded font-medium transition-colors ${
                  filterSeverity === sev
                    ? 'bg-indigo-600 text-white'
                    : 'bg-white text-slate-600 hover:bg-slate-100 border border-slate-200'
                }`}
              >
                {sev === 'ALL' ? 'All' : sev}
              </button>
            ))}
          </div>
        </div>

        {filteredFindings.length === 0 ? (
          <div className="p-4 bg-white rounded-lg border border-slate-200 text-center">
            <CheckCircle2 className="w-6 h-6 text-emerald-500 mx-auto mb-1" />
            <p className="text-xs font-medium text-slate-700">No findings matching the selected filter.</p>
            <p className="text-[11px] text-slate-400">All applicable validation rules passed successfully.</p>
          </div>
        ) : (
          <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
            {filteredFindings.map((finding: ValidationFinding, idx: number) => {
              const isError = finding.severity === 'ERROR';
              const isWarning = finding.severity === 'WARNING';

              return (
                <div
                  key={`${finding.rule_id}-${finding.field}-${idx}`}
                  className={`p-3 rounded-lg border text-xs space-y-1.5 ${
                    isError
                      ? 'bg-rose-50/60 border-rose-200 text-rose-950'
                      : isWarning
                      ? 'bg-amber-50/60 border-amber-200 text-amber-950'
                      : 'bg-sky-50/60 border-sky-200 text-sky-950'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span
                        className={`font-semibold px-1.5 py-0.5 rounded text-[10px] tracking-wider uppercase ${
                          isError
                            ? 'bg-rose-200 text-rose-800'
                            : isWarning
                            ? 'bg-amber-200 text-amber-800'
                            : 'bg-sky-200 text-sky-800'
                        }`}
                      >
                        {finding.severity}
                      </span>
                      <span className="font-mono font-medium text-slate-700 text-[11px]">
                        {finding.field}
                      </span>
                    </div>

                    <span className="font-mono text-[10px] text-slate-400">
                      {finding.rule_id}
                    </span>
                  </div>

                  <p className="text-xs font-medium leading-relaxed">
                    {finding.message}
                  </p>

                  {finding.suggestion && (
                    <div className="flex items-start gap-1 text-[11px] text-slate-600 bg-white/70 p-2 rounded border border-slate-200/60">
                      <ChevronRight className="w-3.5 h-3.5 text-indigo-500 shrink-0 mt-0.5" />
                      <span>
                        <strong className="text-slate-800">Suggestion:</strong> {finding.suggestion}
                      </span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Audit & Disclaimer Notice */}
      <div className="pt-2 border-t border-slate-200 text-[11px] text-slate-400 flex items-start gap-1.5">
        <Info className="w-3.5 h-3.5 text-slate-400 shrink-0 mt-0.5" />
        <p>
          Deterministic Validation Engine v1.0.0 evaluates syntax, required fields, and structural consistency. It does not perform authoritative tax authority lookups or make an onboarding decision (Approved/Rejected).
        </p>
      </div>
    </div>
  );
};
