import React, { useState } from 'react';
import { Header } from './components/Header';
import { VendorForm } from './components/VendorForm';
import { VendorList } from './components/VendorList';
import { Footer } from './components/Footer';
import {
  Shield,
  Sparkles,
  Database,
  FileCheck,
  Building2,
  ListFilter,
} from 'lucide-react';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'directory' | 'register'>('directory');
  const [directoryRefreshTrigger, setDirectoryRefreshTrigger] = useState(0);

  const handleVendorCreated = () => {
    setDirectoryRefreshTrigger((prev) => prev + 1);
  };

  return (
    <div className="min-h-screen flex flex-col bg-slate-50">
      <Header />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        {/* Hero Section */}
        <div className="bg-gradient-to-r from-slate-900 via-sky-950 to-slate-900 text-white rounded-2xl p-8 sm:p-10 shadow-lg relative overflow-hidden">
          <div className="absolute top-0 right-0 -mt-10 -mr-10 w-80 h-80 bg-sky-500/10 rounded-full blur-3xl pointer-events-none" />
          <div className="relative z-10 max-w-3xl">
            <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-full bg-sky-500/20 text-sky-300 text-xs font-semibold mb-4 border border-sky-400/30">
              <Sparkles className="w-3.5 h-3.5" />
              <span>Enterprise Compliance & Verification</span>
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
                <span>Bank-Grade Encryption</span>
              </div>
              <div className="flex items-center space-x-1.5">
                <FileCheck className="w-4 h-4 text-sky-400" />
                <span>Intelligent Document OCR</span>
              </div>
            </div>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-2 rounded-xl shadow-sm">
          <nav className="flex space-x-2">
            <button
              type="button"
              onClick={() => setActiveTab('directory')}
              className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold transition-all ${
                activeTab === 'directory'
                  ? 'bg-sky-600 text-white shadow-sm'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
              }`}
            >
              <ListFilter className="w-4 h-4" />
              <span>Vendor Directory</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab('register')}
              className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold transition-all ${
                activeTab === 'register'
                  ? 'bg-sky-600 text-white shadow-sm'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
              }`}
            >
              <Building2 className="w-4 h-4" />
              <span>Register Vendor</span>
            </button>
          </nav>

          <div className="hidden md:flex items-center gap-2 text-[11px] text-slate-500">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-100 font-medium">
              <Shield className="w-3.5 h-3.5 text-emerald-600" />
              AES-256 Encrypted Storage
            </span>
          </div>
        </div>

        {/* Tab Content */}
        {activeTab === 'directory' && (
          <VendorList
            key={directoryRefreshTrigger}
            onNavigateToForm={() => setActiveTab('register')}
          />
        )}

        {activeTab === 'register' && (
          <VendorForm
            onVendorCreated={handleVendorCreated}
            onNavigateToDirectory={() => setActiveTab('directory')}
          />
        )}
      </main>

      <Footer />
    </div>
  );
};

export default App;
