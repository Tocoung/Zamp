import React from 'react';
import { Header } from './components/Header';
import { BackendStatus } from './components/BackendStatus';
import { ArchitectureRoadmap } from './components/ArchitectureRoadmap';
import { Footer } from './components/Footer';
import { Shield, Sparkles, Database, FileCheck, ArrowRight } from 'lucide-react';

export const App: React.FC = () => {
  return (
    <div className="min-h-screen flex flex-col bg-slate-50">
      <Header />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        {/* Hero Section */}
        <div className="bg-gradient-to-r from-slate-900 via-sky-950 to-slate-900 text-white rounded-2xl p-8 sm:p-10 shadow-lg relative overflow-hidden">
          <div className="absolute top-0 right-0 -mt-10 -mr-10 w-80 h-80 bg-sky-500/10 rounded-full blur-3xl pointer-events-none" />
          <div className="relative z-10 max-w-3xl">
            <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-full bg-sky-500/20 text-sky-300 text-xs font-semibold mb-4 border border-sky-400/30">
              <Sparkles className="w-3.5 h-3.5" />
              <span>Zamp AI Solutions Analyst Case Study</span>
            </div>
            <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-white">
              Autonomous Vendor Onboarding Automation
            </h1>
            <p className="mt-4 text-sm sm:text-base text-slate-300 leading-relaxed">
              An intelligent, fault-tolerant orchestration platform designed to streamline vendor company registration,
              tax identification, banking data verification, and multi-format compliance document audits with human-in-the-loop oversight.
            </p>

            <div className="mt-6 flex flex-wrap gap-4 text-xs text-slate-300 font-medium">
              <div className="flex items-center space-x-1.5">
                <Shield className="w-4 h-4 text-sky-400" />
                <span>Deterministic Verification</span>
              </div>
              <div className="flex items-center space-x-1.5">
                <Database className="w-4 h-4 text-sky-400" />
                <span>Extensible Persistence</span>
              </div>
              <div className="flex items-center space-x-1.5">
                <FileCheck className="w-4 h-4 text-sky-400" />
                <span>Document Extraction Architecture</span>
              </div>
            </div>
          </div>
        </div>

        {/* Live System Diagnostics */}
        <BackendStatus />

        {/* Roadmap & Architectural Boundaries */}
        <ArchitectureRoadmap />

        {/* Step 1 Scope Clarification Card */}
        <div className="bg-sky-50/60 border border-sky-200/80 rounded-xl p-5 text-xs text-sky-900">
          <div className="font-semibold text-sm flex items-center mb-1 text-sky-950">
            <ArrowRight className="w-4 h-4 mr-1 text-sky-700" />
            Phase 1 — Step 1 Scope Demarcation
          </div>
          <p className="text-sky-800 leading-relaxed">
            In accordance with strict incremental engineering, this step establishes the core API runtime, database connectivity foundation, decoupled directory structure, and environment configuration. Vendor intake forms, validation rules, OCR extraction, and AI decision agents are purposefully deferred to subsequent steps.
          </p>
        </div>
      </main>

      <Footer />
    </div>
  );
};

export default App;
