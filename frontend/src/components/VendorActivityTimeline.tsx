import React from 'react';
import {
  FileText,
  Sparkles,
  Edit3,
  RotateCcw,
  Clock,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Activity,
} from 'lucide-react';
import { VendorActivityItem } from '../config/api';

interface VendorActivityTimelineProps {
  activities: VendorActivityItem[];
  isLoading?: boolean;
}

export const VendorActivityTimeline: React.FC<VendorActivityTimelineProps> = ({
  activities,
  isLoading = false,
}) => {
  const getEventIcon = (eventType: string, status?: string | null) => {
    switch (eventType) {
      case 'VENDOR_SUBMITTED':
        return <Sparkles className="w-4 h-4 text-sky-600" />;
      case 'VENDOR_UPDATED':
        return <Edit3 className="w-4 h-4 text-indigo-600" />;
      case 'DECISION_EXECUTED':
      case 'DECISION_REEVALUATED':
        if (status === 'APPROVED') {
          return <CheckCircle2 className="w-4 h-4 text-emerald-600" />;
        } else if (status === 'PENDING') {
          return <AlertTriangle className="w-4 h-4 text-amber-600" />;
        } else if (status === 'REJECTED') {
          return <XCircle className="w-4 h-4 text-rose-600" />;
        }
        return <RotateCcw className="w-4 h-4 text-slate-600" />;
      default:
        return <FileText className="w-4 h-4 text-slate-500" />;
    }
  };

  const getStatusBadge = (status?: string | null) => {
    if (!status) return null;
    switch (status) {
      case 'APPROVED':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            APPROVED
          </span>
        );
      case 'PENDING':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-50 text-amber-700 border border-amber-200">
            PENDING
          </span>
        );
      case 'REJECTED':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-rose-50 text-rose-700 border border-rose-200">
            REJECTED
          </span>
        );
      case 'SUBMITTED':
      default:
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-sky-50 text-sky-700 border border-sky-200">
            {status}
          </span>
        );
    }
  };

  if (isLoading) {
    return (
      <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 text-center text-xs text-slate-500">
        Loading lifecycle activity timeline...
      </div>
    );
  }

  if (!activities || activities.length === 0) {
    return (
      <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 text-center text-xs text-slate-500">
        No lifecycle events recorded for this vendor yet.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-bold text-slate-600 uppercase tracking-wider flex items-center gap-1.5">
          <Activity className="w-3.5 h-3.5 text-indigo-600" />
          Lifecycle Activity History ({activities.length})
        </h4>
        <span className="text-[11px] text-slate-400">Chronological</span>
      </div>

      <div className="relative pl-6 border-l-2 border-slate-200 space-y-4">
        {activities.map((item, index) => (
          <div key={item.id || index} className="relative group">
            {/* Timeline bullet dot */}
            <div className="absolute -left-[31px] top-1 w-6 h-6 rounded-full bg-white border-2 border-slate-200 group-hover:border-indigo-500 flex items-center justify-center shadow-xs transition-colors">
              {getEventIcon(item.event_type, item.status)}
            </div>

            {/* Event content card */}
            <div className="p-3 rounded-xl bg-slate-50/80 border border-slate-200/80 hover:bg-slate-50 transition-colors">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-slate-800 text-xs">
                    {item.title}
                  </span>
                  {getStatusBadge(item.status)}
                </div>
                <div className="flex items-center gap-1 text-[11px] text-slate-400">
                  <Clock className="w-3 h-3" />
                  <span>{new Date(item.created_at).toLocaleString()}</span>
                </div>
              </div>
              <p className="text-xs text-slate-600 mt-1">
                {item.description}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
