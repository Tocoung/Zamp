import React from 'react';
import { FileText, Cpu, UserCheck, BarChart3, Sparkles, Check, Clock } from 'lucide-react';

interface PhaseItem {
  id: number;
  title: string;
  description: string;
  status: 'active' | 'planned';
  icon: React.ReactNode;
  modules: string[];
}

export const ArchitectureRoadmap: React.FC = () => {
  const phases: PhaseItem[] = [
    {
      id: 1,
      title: 'Phase 1: Foundation & Core Onboarding Engine',
      description: 'Foundation setup, vendor data model & submission, deterministic validation, decision engine, and E2E integration.',
      status: 'active',
      icon: <FileText className="w-5 h-5 text-sky-600" />,
      modules: ['Step 1: Foundation & Probes', 'Vendor Data Model & Submission', 'Deterministic Validation', 'Decision Engine'],
    },
    {
      id: 2,
      title: 'Phase 2: Intelligent Document Processing',
      description: 'Document ingestion, OCR/extraction pipeline, and cross-document verification cross-checks.',
      status: 'planned',
      icon: <Cpu className="w-5 h-5 text-indigo-600" />,
      modules: ['Multi-Document Ingestion', 'OCR & Structured Extraction', 'Cross-Document Verification'],
    },
    {
      id: 3,
      title: 'Phase 3: Exception Handling & Human-in-the-Loop',
      description: 'Automated exception triage, human reviewer console, override workflows, and vendor defect communication.',
      status: 'planned',
      icon: <UserCheck className="w-5 h-5 text-amber-600" />,
      modules: ['Exception Review Queue', 'Human Reviewer Console', 'Vendor Clarification Messaging'],
    },
    {
      id: 4,
      title: 'Phase 4: Product Dashboard & Audit Trail',
      description: 'Operations management portal, searchable immutable audit log, and onboarding lifecycle analytics.',
      status: 'planned',
      icon: <BarChart3 className="w-5 h-5 text-teal-600" />,
      modules: ['Operations Dashboard', 'Immutable Audit Trail', 'Lifecycle Analytics'],
    },
    {
      id: 5,
      title: 'Phase 5: Advanced Intelligence & Production Polish',
      description: 'LLM verification agents, anomaly & fraud scoring, automated resilience tests, and production runbooks.',
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
          const isActive = phase.status === 'active';
          return (
            <div
              key={phase.id}
              className={`p-4 rounded-xl border transition-all ${
                isActive
                  ? 'border-sky-300 bg-sky-50/40 shadow-sm'
                  : 'border-slate-200/80 bg-white hover:border-slate-300'
              }`}
            >
              <div className="flex items-start justify-between">
                <div className="flex items-start space-x-3">
                  <div
                    className={`p-2 rounded-lg ${
                      isActive ? 'bg-sky-100 text-sky-700' : 'bg-slate-100 text-slate-600'
                    }`}
                  >
                    {phase.icon}
                  </div>
                  <div>
                    <div className="flex items-center space-x-2">
                      <h3 className="text-sm font-semibold text-slate-900">
                        {phase.title}
                      </h3>
                      {isActive ? (
                        <span className="inline-flex items-center text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-sky-100 text-sky-800 border border-sky-300">
                          <Check className="w-3 h-3 mr-1" /> Current Step
                        </span>
                      ) : (
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
