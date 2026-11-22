import React from 'react';

export const Footer: React.FC = () => {
  return (
    <footer className="mt-12 border-t border-slate-200 bg-white py-6">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between text-xs text-slate-500">
        <p>
          © 2026 Zamp Inc. • Enterprise Vendor Onboarding & Compliance Automation
        </p>
        <p className="mt-2 sm:mt-0 font-medium text-[11px] text-slate-400">
          Bank-grade AES-256 Encryption • Automated Document Intelligence
        </p>
      </div>
    </footer>
  );
};
