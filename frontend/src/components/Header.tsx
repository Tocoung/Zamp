import React from 'react';
import { CheckCircle2, Shield } from 'lucide-react';

export const Header: React.FC = () => {
  return (
    <header className="border-b border-slate-200 bg-white sticky top-0 z-50 shadow-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-lg bg-sky-600 flex items-center justify-center text-white font-bold text-xl shadow-sm">
            Z
          </div>
          <div>
            <h1 className="text-lg font-bold text-slate-900 leading-tight">
              Zamp
            </h1>
            <p className="text-xs text-slate-500 font-medium">
              Enterprise Vendor Onboarding & Compliance Automation
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            <CheckCircle2 className="w-3.5 h-3.5 mr-1 text-emerald-600" />
            Automated Compliance Active
          </span>
          <span className="hidden sm:inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-700 border border-slate-200">
            <Shield className="w-3.5 h-3.5 mr-1 text-slate-600" />
            AES-256 Encrypted
          </span>
        </div>
      </div>
    </header>
  );
};
