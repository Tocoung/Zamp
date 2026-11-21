import React, { useState } from 'react';
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  ArrowRight,
  History,
  ShieldCheck,
  Clock,
  Sparkles,
  Info,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import {
  DecisionResult,
  DecisionHistoryItem,
  DecisionStatus,
} from '../config/api';

interface DecisionReportProps {
  decision: DecisionResult;
  history?: DecisionHistoryItem[];
  onReevaluate?: () => void;
  isEvaluating?: boolean;
}

export const DecisionReport: React.FC<DecisionReportProps> = ({
  decision,
  history = [],
  onReevaluate,
  isEvaluating = false,
}) => {
  const [showHistory, setShowHistory] = useState(false);

  const getStatusPresentation = (status: DecisionStatus) => {
    switch (status) {
      case 'APPROVED':
        return {
          badgeBg: 'bg-emerald-50 text-emerald-800 border-emerald-200',
          containerBg: 'border-emerald-200 bg-emerald-50/30',
          icon: <CheckCircle2 className="w-5 h-5 text-emerald-600" />,
          title: 'Onboarding Approved',
          subtitle: 'All deterministic validation and business rules satisfied',
        };
      case 'PENDING':
        return {
          badgeBg: 'bg-amber-50 text-amber-800 border-amber-200',
          containerBg: 'border-amber-200 bg-amber-50/30',
          icon: <AlertTriangle className="w-5 h-5 text-amber-600" />,
          title: 'Decision Pending Review',
          subtitle: 'Review required before vendor onboarding can proceed',
        };
      case 'REJECTED':
      default:
        return {
          badgeBg: 'bg-rose-50 text-rose-800 border-rose-200',
          containerBg: 'border-rose-200 bg-rose-50/30',
          icon: <XCircle className="w-5 h-5 text-rose-600" />,
          title: 'Onboarding Rejected',
          subtitle: 'Blocking statutory or structural rules were violated',
        };
    }
  };

  const presentation = getStatusPresentation(decision.status);

  return (
    <div className={`border rounded-xl p-5 space-y-4 ${presentation.containerBg}`}>
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-200 pb-4">
        <div className="flex items-start gap-3">
          <div className="p-2 rounded-lg bg-white shadow-xs border border-slate-200">
            {presentation.icon}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-bold text-slate-900 text-base">
                {presentation.title}
              </h3>
              <span
                className={`px-2.5 py-0.5 rounded-full text-xs font-semibold border ${presentation.badgeBg}`}
              >
                {decision.status}
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              Decision v{decision.decision_version} &bull; Validated with Ruleset v
              {decision.ruleset_version} ({decision.validation_status}) &bull;{' '}
              {new Date(decision.decided_at).toLocaleString()}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {onReevaluate && (
            <button
              onClick={onReevaluate}
              disabled={isEvaluating}
              className="px-3 py-1.5 text-xs font-medium rounded-lg bg-white hover:bg-slate-50 text-slate-700 border border-slate-200 shadow-xs transition-colors disabled:opacity-50 flex items-center gap-1.5"
            >
              <Sparkles className="w-3.5 h-3.5 text-indigo-500" />
              <span>{isEvaluating ? 'Evaluating...' : 'Re-evaluate'}</span>
            </button>
          )}

          {history.length > 1 && (
            <button
              onClick={() => setShowHistory(!showHistory)}
              className="px-2.5 py-1.5 text-xs font-medium rounded-lg bg-white hover:bg-slate-50 text-slate-600 border border-slate-200 shadow-xs transition-colors flex items-center gap-1"
            >
              <History className="w-3.5 h-3.5 text-slate-500" />
              <span>History ({history.length})</span>
              {showHistory ? (
                <ChevronUp className="w-3 h-3 text-slate-400" />
              ) : (
                <ChevronDown className="w-3 h-3 text-slate-400" />
              )}
            </button>
          )}
        </div>
      </div>

      {/* Decision Reasons Section */}
      <div className="space-y-2">
        <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider flex items-center gap-1.5">
          <ShieldCheck className="w-3.5 h-3.5 text-slate-400" />
          Decision Reasons ({decision.reasons.length})
        </h4>

        <div className="space-y-2">
          {decision.reasons.map((reason, idx) => {
            const isError = reason.severity === 'ERROR';
            const isWarning = reason.severity === 'WARNING';

            return (
              <div
                key={`${reason.code}-${idx}`}
                className={`p-3 rounded-lg border text-xs space-y-1 ${
                  isError
                    ? 'bg-rose-50/80 border-rose-200 text-rose-950'
                    : isWarning
                    ? 'bg-amber-50/80 border-amber-200 text-amber-950'
                    : 'bg-white border-slate-200 text-slate-800'
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
                          : 'bg-emerald-100 text-emerald-800'
                      }`}
                    >
                      {reason.severity}
                    </span>
                    <span className="font-semibold text-slate-900 text-xs">
                      {reason.title}
                    </span>
                  </div>
                  <span className="font-mono text-[10px] text-slate-400">
                    {reason.code}
                  </span>
                </div>
                <p className="text-xs text-slate-600 leading-relaxed">
                  {reason.explanation}
                </p>
                {reason.source_rule_id && (
                  <p className="text-[10px] text-slate-400 font-mono">
                    Source Rule: {reason.source_rule_id}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Actionable Recommendations Section */}
      {decision.recommendations.length > 0 && (
        <div className="space-y-2 pt-2 border-t border-slate-200">
          <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider flex items-center gap-1.5">
            <ArrowRight className="w-3.5 h-3.5 text-slate-400" />
            Actionable Next Steps ({decision.recommendations.length})
          </h4>

          <div className="space-y-2">
            {decision.recommendations.map((rec, idx) => {
              const isHigh = rec.priority === 'HIGH';
              const isMedium = rec.priority === 'MEDIUM';

              return (
                <div
                  key={`${rec.action}-${idx}`}
                  className="bg-white p-3 rounded-lg border border-slate-200 shadow-xs flex items-start gap-3"
                >
                  <span
                    className={`shrink-0 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                      isHigh
                        ? 'bg-rose-100 text-rose-800'
                        : isMedium
                        ? 'bg-amber-100 text-amber-800'
                        : 'bg-indigo-100 text-indigo-800'
                    }`}
                  >
                    {rec.priority}
                  </span>
                  <div className="space-y-0.5 text-xs">
                    <p className="font-semibold text-slate-900 font-mono text-[11px]">
                      {rec.action}
                    </p>
                    <p className="text-slate-600 leading-relaxed">
                      {rec.description}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Decision Audit History Collapsible */}
      {showHistory && history.length > 0 && (
        <div className="pt-3 border-t border-slate-200 space-y-2">
          <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5 text-slate-400" />
            Decision Audit History ({history.length} records)
          </h4>

          <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
            {history.map((histItem) => (
              <div
                key={histItem.id}
                className="bg-white/80 p-2.5 rounded-lg border border-slate-200 text-xs flex items-center justify-between gap-3"
              >
                <div className="flex items-center gap-2">
                  <span
                    className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                      histItem.status === 'APPROVED'
                        ? 'bg-emerald-100 text-emerald-800'
                        : histItem.status === 'PENDING'
                        ? 'bg-amber-100 text-amber-800'
                        : 'bg-rose-100 text-rose-800'
                    }`}
                  >
                    {histItem.status}
                  </span>
                  <span className="text-slate-500 text-[11px]">
                    v{histItem.decision_version} &bull; {histItem.reason_codes.length} reasons
                  </span>
                </div>
                <span className="text-[10px] text-slate-400 font-mono">
                  {new Date(histItem.decided_at).toLocaleString()}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Non-authoritative Disclaimer */}
      <div className="pt-2 border-t border-slate-200 text-[11px] text-slate-400 flex items-start gap-1.5">
        <Info className="w-3.5 h-3.5 text-slate-400 shrink-0 mt-0.5" />
        <p>
          Deterministic Decision Engine v{decision.decision_version} applies policy thresholds to syntax and format validation. An 'APPROVED' outcome indicates deterministic onboarding checks passed without blocking conditions, but does not constitute authoritative tax registration verification or bank ownership guarantee.
        </p>
      </div>
    </div>
  );
};
