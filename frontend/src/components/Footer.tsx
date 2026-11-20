import React from 'react';

export const Footer: React.FC = () => {
  return (
    <footer className="mt-12 border-t border-slate-200 bg-white py-6">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between text-xs text-slate-500">
        <p>
          © 2026 Zamp AI Solutions Analyst Case Study • Vendor Onboarding Automation
        </p>
        <p className="mt-2 sm:mt-0 font-mono text-[11px]">
          Stack: React (TypeScript) + FastAPI + SQLite/PostgreSQL
        </p>
      </div>
    </footer>
  );
};
