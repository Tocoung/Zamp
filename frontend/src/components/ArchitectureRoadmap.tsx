import React from 'react';
import { FileText, Cpu, UserCheck, BarChart3, Sparkles, Check, CheckCircle2, Clock } from 'lucide-react';

interface PhaseItem {
  id: number;
  title: string;
  description: string;
  status: 'completed' | 'active' | 'planned';
  icon: React.ReactNode;
  modules: string[];
}

export const ArchitectureRoadmap: React.FC = () => {
  const phases: PhaseItem[] = [
    {
      id: 1,
      title: 'Phase 1: Foundation & Core Onboarding Engine',
      description: 'Statutory entity data validation, AES-256 financial data encryption at rest, deterministic decision engine, and lifecycle audit timeline.',
      status: 'completed',
      icon: <FileText className="w-5 h-5 text-emerald-600" />,
      modules: ['Entity Model & Intake', 'Deterministic Validation Engine', 'Decision & Recommendation Engine', 'Activity Timeline & Audit History'],
    },
    {
      id: 2,
      title: 'Phase 2: Intelligent Document Processing & Evidence Scoring',
      description: 'Multi-document intake & encryption, deterministic document classification, multi-format OCR extraction, and field-level evidence quality scoring.',
      status: 'active',
      icon: <Cpu className="w-5 h-5 text-sky-600" />,
      modules: ['Multi-Document Intake & Encryption', 'Deterministic Classification', 'OCR & Structured Extraction', 'Field Evidence & Quality Scoring'],
    },
    {
      id: 3,
      title: 'Phase 3: Exception Handling & Human-in-the-Loop',
      description: 'Cross-document discrepancy detection, exception triage queue, human reviewer console, and vendor correction workflows.',
      status: 'planned',
      icon: <UserCheck className="w-5 h-5 text-amber-600" />,
      modules: ['Cross-Document Verification', 'Reviewer Override Console', 'Vendor Clarification Messaging'],
    },
    {
      id: 4,
      title: 'Phase 4: Operations Analytics & Audit Trail',
      description: 'Operations management portal, immutable audit logs, and procurement onboarding lifecycle metrics.',
      status: 'planned',
      icon: <BarChart3 className="w-5 h-5 text-teal-600" />,
      modules: ['Operations Dashboard', 'Immutable Audit Trail', 'Lifecycle Analytics'],
    },
    {
      id: 5,
      title: 'Phase 5: Advanced Intelligence & Enterprise Hardening',
      description: 'LLM verification assistance, anomaly & fraud scoring, automated resilience benchmarks, and multi-tenant security.',
      status: 'planned',
      icon: <Sparkles className="w-5 h-5 text-purple-600" />,
      modules: ['LLM Verification Agents', 'Fraud & Anomaly Scoring', 'Production Hardening'],
    },
  ];

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
      <div className="mb-6">
        <h2 className="text-base font-semibold text-slate-800">
          Incremental Architecture & Phase Roadmap
        </h2>
        <p className="text-xs text-slate-500 mt-1">
          Designed strictly for progressive delivery without architectural rework.
        </p>
      </div>

      <div className="space-y-4">
        {phases.map((phase) => {
          const isCompleted = phase.status === 'completed';
          const isActive = phase.status === 'active';

          return (
            <div
              key={phase.id}
              className={`p-4 rounded-xl border transition-all ${
                isActive
                  ? 'border-sky-300 bg-sky-50/40 shadow-sm'
                  : isCompleted
                  ? 'border-emerald-200/80 bg-emerald-50/30'
                  : 'border-slate-200/80 bg-white hover:border-slate-300'
              }`}
            >
              <div className="flex items-start justify-between">
                <div className="flex items-start space-x-3">
                  <div
                    className={`p-2 rounded-lg ${
                      isActive
                        ? 'bg-sky-100 text-sky-700'
                        : isCompleted
                        ? 'bg-emerald-100 text-emerald-700'
                        : 'bg-slate-100 text-slate-600'
                    }`}
                  >
                    {phase.icon}
                  </div>
                  <div>
                    <div className="flex items-center space-x-2">
                      <h3 className="text-sm font-semibold text-slate-900">
                        {phase.title}
                      </h3>
                      {isActive && (
                        <span className="inline-flex items-center text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-sky-100 text-sky-800 border border-sky-300">
                          <Check className="w-3 h-3 mr-1" /> Current Delivered Phase
                        </span>
                      )}
                      {isCompleted && (
                        <span className="inline-flex items-center text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 border border-emerald-300">
                          <CheckCircle2 className="w-3 h-3 mr-1" /> Completed
                        </span>
                      )}
                      {!isActive && !isCompleted && (
                        <span className="inline-flex items-center text-[10px] font-medium px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">
                          <Clock className="w-3 h-3 mr-1" /> Upcoming
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-slate-600 mt-1 leading-relaxed">
                      {phase.description}
                    </p>
                  </div>
                </div>
              </div>

              {/* Module boundary tags */}
              <div className="mt-3 pt-3 border-t border-slate-200/60 flex flex-wrap gap-1.5">
                {phase.modules.map((mod, idx) => (
                  <span
                    key={idx}
                    className={`text-[11px] font-medium px-2 py-0.5 rounded-md border ${
                      isActive
                        ? 'bg-sky-100/60 text-sky-800 border-sky-200'
                        : isCompleted
                        ? 'bg-emerald-100/40 text-emerald-800 border-emerald-200'
                        : 'bg-slate-50 text-slate-600 border-slate-200'
                    }`}
                  >
                    {mod}
                  </span>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
