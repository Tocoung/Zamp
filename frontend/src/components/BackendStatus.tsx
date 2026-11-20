import React, { useEffect, useState } from 'react';
import { Activity, Database, Server, RefreshCw, CheckCircle2, AlertCircle, XCircle } from 'lucide-react';
import { fetchHealthStatus, HealthStatus, API_BASE_URL } from '../config/api';

export const BackendStatus: React.FC = () => {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [lastChecked, setLastChecked] = useState<string>('');

  const loadStatus = async () => {
    setLoading(true);
    const data = await fetchHealthStatus();
    setHealth(data);
    setLastChecked(new Date().toLocaleTimeString());
    setLoading(false);
  };

  useEffect(() => {
    loadStatus();
    const interval = setInterval(loadStatus, 15000);
    return () => clearInterval(interval);
  }, []);

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'healthy':
      case 'connected':
        return (
          <span className="inline-flex items-center text-xs font-semibold text-emerald-700 bg-emerald-50 px-2.5 py-1 rounded-md border border-emerald-200">
            <CheckCircle2 className="w-3.5 h-3.5 mr-1 text-emerald-600" />
            {status.toUpperCase()}
          </span>
        );
      case 'degraded':
      case 'disconnected':
        return (
          <span className="inline-flex items-center text-xs font-semibold text-amber-700 bg-amber-50 px-2.5 py-1 rounded-md border border-amber-200">
            <AlertCircle className="w-3.5 h-3.5 mr-1 text-amber-600" />
            {status.toUpperCase()}
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center text-xs font-semibold text-rose-700 bg-rose-50 px-2.5 py-1 rounded-md border border-rose-200">
            <XCircle className="w-3.5 h-3.5 mr-1 text-rose-600" />
            OFFLINE
          </span>
        );
    }
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
      <div className="flex items-center justify-between pb-4 border-b border-slate-100">
        <div className="flex items-center space-x-2">
          <Activity className="w-5 h-5 text-sky-600" />
          <h2 className="text-base font-semibold text-slate-800">
            System & Infrastructure Health
          </h2>
        </div>
        <button
          onClick={loadStatus}
          disabled={loading}
          className="inline-flex items-center text-xs font-medium text-slate-600 hover:text-slate-900 bg-slate-50 hover:bg-slate-100 px-3 py-1.5 rounded-lg border border-slate-200 transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
        {/* API Backend Status */}
        <div className="p-4 rounded-lg bg-slate-50 border border-slate-200/60">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-slate-500 flex items-center">
              <Server className="w-4 h-4 mr-1.5 text-slate-400" />
              FastAPI Core Service
            </span>
            {health ? getStatusBadge(health.status) : <span className="text-xs text-slate-400">Checking...</span>}
          </div>
          <div className="text-xs text-slate-600 font-mono mt-2 truncate">
            {API_BASE_URL}
          </div>
        </div>

        {/* Database Status */}
        <div className="p-4 rounded-lg bg-slate-50 border border-slate-200/60">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-slate-500 flex items-center">
              <Database className="w-4 h-4 mr-1.5 text-slate-400" />
              Database Engine
            </span>
            {health ? getStatusBadge(health.database) : <span className="text-xs text-slate-400">Checking...</span>}
          </div>
          <div className="text-xs text-slate-600 font-mono mt-2">
            SQLAlchemy (SQLite / PostgreSQL)
          </div>
        </div>

        {/* Environment Details */}
        <div className="p-4 rounded-lg bg-slate-50 border border-slate-200/60">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-slate-500">
              Runtime Environment
            </span>
            <span className="text-xs font-semibold text-slate-700 bg-slate-200/70 px-2 py-0.5 rounded">
              {health?.environment || 'development'}
            </span>
          </div>
          <div className="text-xs text-slate-500 flex justify-between mt-2">
            <span>Version: {health?.version || '0.1.0'}</span>
            <span>Last checked: {lastChecked || 'just now'}</span>
          </div>
        </div>
      </div>
    </div>
  );
};
