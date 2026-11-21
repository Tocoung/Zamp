import React, { useState, useEffect, useRef } from 'react';
import {
  FileText,
  Upload,
  Download,
  Trash2,
  AlertCircle,
  CheckCircle2,
  Loader2,
  File,
  FileImage,
  Shield,
  Layers,
  Sparkles,
  ChevronDown,
  ChevronRight,
  AlertTriangle,
  Info,
} from 'lucide-react';
import {
  VendorDocumentResponse,
  DocumentCategory,
  ClassificationStatus,
  fetchVendorDocuments,
  uploadVendorDocument,
  downloadVendorDocument,
  deleteVendorDocument,
  classifyVendorDocument,
} from '../config/api';

interface DocumentManagerProps {
  vendorId: string;
  onActivityChange?: () => void;
}

const CATEGORY_LABELS: Record<DocumentCategory, string> = {
  TAX_CERTIFICATE: 'Tax Certificate',
  BANK_PROOF: 'Bank Proof / Voided Cheque',
  CERTIFICATE_OF_INCORPORATION: 'Certificate of Incorporation',
  ADDRESS_PROOF: 'Proof of Address',
  OTHER: 'Other Supporting Document',
  UNKNOWN: 'Unspecified',
};

function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}

export const DocumentManager: React.FC<DocumentManagerProps> = ({
  vendorId,
  onActivityChange,
}) => {
  const [documents, setDocuments] = useState<VendorDocumentResponse[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [selectedCategory, setSelectedCategory] = useState<DocumentCategory>('TAX_CERTIFICATE');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [classifyingId, setClassifyingId] = useState<string | null>(null);
  const [expandedClassificationId, setExpandedClassificationId] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadDocuments = async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const data = await fetchVendorDocuments(vendorId);
      setDocuments(data.items);
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to load vendor documents');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadDocuments();
  }, [vendorId]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const file = e.target.files[0];
      if (file.size > 10 * 1024 * 1024) {
        setErrorMessage('File exceeds the 10 MB maximum allowed size');
        setSelectedFile(null);
        if (fileInputRef.current) fileInputRef.current.value = '';
        return;
      }
      setSelectedFile(file);
      setErrorMessage(null);
      setSuccessMessage(null);
    }
  };

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile || isUploading) return;

    setIsUploading(true);
    setErrorMessage(null);
    setSuccessMessage(null);

    try {
      const uploadedDoc = await uploadVendorDocument(
        vendorId,
        selectedFile,
        selectedCategory
      );
      setSuccessMessage(
        `Document '${uploadedDoc.original_filename}' uploaded and securely stored.`
      );
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      await loadDocuments();
      if (onActivityChange) onActivityChange();
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to upload document');
    } finally {
      setIsUploading(false);
    }
  };

  const handleDownload = async (doc: VendorDocumentResponse) => {
    setDownloadingId(doc.id);
    setErrorMessage(null);
    try {
      await downloadVendorDocument(vendorId, doc.id, doc.original_filename);
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to download document');
    } finally {
      setDownloadingId(null);
    }
  };

  const handleDelete = async (doc: VendorDocumentResponse) => {
    if (!window.confirm(`Are you sure you want to delete '${doc.original_filename}'?`)) {
      return;
    }

    setDeletingId(doc.id);
    setErrorMessage(null);
    try {
      await deleteVendorDocument(vendorId, doc.id);
      setSuccessMessage(`Document '${doc.original_filename}' deleted.`);
      if (expandedClassificationId === doc.id) {
        setExpandedClassificationId(null);
      }
      await loadDocuments();
      if (onActivityChange) onActivityChange();
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to delete document');
    } finally {
      setDeletingId(null);
    }
  };

  const handleClassify = async (doc: VendorDocumentResponse) => {
    setClassifyingId(doc.id);
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      const result = await classifyVendorDocument(vendorId, doc.id);
      setDocuments((prev) =>
        prev.map((d) => (d.id === doc.id ? { ...d, latest_classification: result } : d))
      );
      setExpandedClassificationId(doc.id);
      setSuccessMessage(
        `Classification complete for '${doc.original_filename}': ${CATEGORY_LABELS[result.predicted_category as DocumentCategory] || result.predicted_category} (${result.status}, ${Math.round(result.confidence_score * 100)}%)`
      );
      if (onActivityChange) onActivityChange();
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to classify document');
    } finally {
      setClassifyingId(null);
    }
  };

  const getCategoryBadge = (category: string) => {
    const label = CATEGORY_LABELS[category as DocumentCategory] || category;
    switch (category) {
      case 'TAX_CERTIFICATE':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-purple-50 text-purple-700 border border-purple-200">
            {label}
          </span>
        );
      case 'BANK_PROOF':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            {label}
          </span>
        );
      case 'CERTIFICATE_OF_INCORPORATION':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-sky-50 text-sky-700 border border-sky-200">
            {label}
          </span>
        );
      case 'ADDRESS_PROOF':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-50 text-amber-700 border border-amber-200">
            {label}
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-700 border border-slate-200">
            {label}
          </span>
        );
    }
  };

  const getClassificationStatusBadge = (status: ClassificationStatus) => {
    switch (status) {
      case 'CLASSIFIED':
        return (
          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            <CheckCircle2 className="w-2.5 h-2.5 text-emerald-600" />
            Classified
          </span>
        );
      case 'LOW_CONFIDENCE':
        return (
          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-amber-50 text-amber-700 border border-amber-200">
            <AlertTriangle className="w-2.5 h-2.5 text-amber-600" />
            Low Confidence
          </span>
        );
      case 'INSUFFICIENT_TEXT':
        return (
          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-600 border border-slate-300">
            <Info className="w-2.5 h-2.5 text-slate-500" />
            Insufficient Text
          </span>
        );
      case 'FAILED':
        return (
          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-rose-50 text-rose-700 border border-rose-200">
            <AlertCircle className="w-2.5 h-2.5 text-rose-600" />
            Failed
          </span>
        );
      default:
        return null;
    }
  };

  const getFileIcon = (mimeType: string) => {
    if (mimeType.includes('pdf')) {
      return <FileText className="w-4 h-4 text-rose-600 shrink-0" />;
    }
    if (mimeType.includes('image')) {
      return <FileImage className="w-4 h-4 text-indigo-600 shrink-0" />;
    }
    return <File className="w-4 h-4 text-slate-500 shrink-0" />;
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between pb-2 border-b border-slate-200">
        <div>
          <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider flex items-center gap-1.5">
            <Shield className="w-3.5 h-3.5 text-sky-600" />
            Supporting Documents & Classification
          </h4>
          <p className="text-[11px] text-slate-500 mt-0.5">
            Encrypted storage (AES-128-CBC + HMAC) and deterministic content classification.
          </p>
        </div>
        <span className="text-[11px] font-semibold text-slate-500 bg-slate-100 px-2.5 py-1 rounded-md">
          {documents.length} {documents.length === 1 ? 'file' : 'files'}
        </span>
      </div>

      {/* Alert Banners */}
      {errorMessage && (
        <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
            <span>{errorMessage}</span>
          </div>
          <button
            type="button"
            onClick={() => setErrorMessage(null)}
            className="text-rose-500 hover:text-rose-700 text-xs font-bold"
          >
            ✕
          </button>
        </div>
      )}

      {successMessage && (
        <div className="p-3 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
            <span>{successMessage}</span>
          </div>
          <button
            type="button"
            onClick={() => setSuccessMessage(null)}
            className="text-emerald-500 hover:text-emerald-700 text-xs font-bold"
          >
            ✕
          </button>
        </div>
      )}

      {/* Upload Box */}
      <form
        onSubmit={handleUpload}
        className="p-3.5 rounded-xl bg-slate-50/80 border border-slate-200 space-y-3"
      >
        <div className="grid grid-cols-1 sm:grid-cols-12 gap-3 items-end">
          <div className="sm:col-span-5">
            <label className="block text-[11px] font-semibold text-slate-600 mb-1">
              Document Category *
            </label>
            <select
              value={selectedCategory}
              onChange={(e) => setSelectedCategory(e.target.value as DocumentCategory)}
              disabled={isUploading}
              className="w-full text-xs px-2.5 py-1.5 rounded-lg border border-slate-300 bg-white text-slate-800 focus:outline-none focus:ring-1 focus:ring-sky-500"
            >
              <option value="TAX_CERTIFICATE">{CATEGORY_LABELS.TAX_CERTIFICATE} (GST/PAN/W-9)</option>
              <option value="BANK_PROOF">{CATEGORY_LABELS.BANK_PROOF}</option>
              <option value="CERTIFICATE_OF_INCORPORATION">{CATEGORY_LABELS.CERTIFICATE_OF_INCORPORATION}</option>
              <option value="ADDRESS_PROOF">{CATEGORY_LABELS.ADDRESS_PROOF}</option>
              <option value="OTHER">{CATEGORY_LABELS.OTHER}</option>
            </select>
          </div>

          <div className="sm:col-span-4">
            <label className="block text-[11px] font-semibold text-slate-600 mb-1">
              Choose File (PDF, PNG, JPG) *
            </label>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
              onChange={handleFileChange}
              disabled={isUploading}
              className="w-full text-xs text-slate-600 file:mr-2 file:py-1 file:px-2.5 file:rounded-md file:border-0 file:text-[11px] file:font-semibold file:bg-sky-50 file:text-sky-700 hover:file:bg-sky-100 cursor-pointer"
            />
          </div>

          <div className="sm:col-span-3">
            <button
              type="submit"
              disabled={!selectedFile || isUploading}
              className="w-full inline-flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-sky-600 hover:bg-sky-700 text-white shadow-xs transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isUploading ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Uploading...</span>
                </>
              ) : (
                <>
                  <Upload className="w-3.5 h-3.5" />
                  <span>Upload Document</span>
                </>
              )}
            </button>
          </div>
        </div>
      </form>

      {/* Documents Table */}
      <div className="border border-slate-200 rounded-xl overflow-hidden bg-white shadow-2xs">
        {isLoading ? (
          <div className="p-8 text-center text-slate-400 flex items-center justify-center gap-2 text-xs">
            <Loader2 className="w-4 h-4 animate-spin text-slate-500" />
            <span>Loading documents...</span>
          </div>
        ) : documents.length === 0 ? (
          <div className="p-8 text-center text-slate-500 text-xs space-y-1">
            <Layers className="w-6 h-6 mx-auto text-slate-300" />
            <p className="font-medium text-slate-700">No supporting documents uploaded yet</p>
            <p className="text-[11px] text-slate-400">
              Upload tax certificates, incorporation papers, or banking proof above.
            </p>
          </div>
        ) : (
          <table className="w-full text-left text-xs divide-y divide-slate-200">
            <thead className="bg-slate-50 text-slate-600 text-[11px] font-semibold uppercase tracking-wider">
              <tr>
                <th scope="col" className="px-4 py-2.5">
                  Document
                </th>
                <th scope="col" className="px-3 py-2.5">
                  Declared
                </th>
                <th scope="col" className="px-3 py-2.5">
                  Classification & Evidence
                </th>
                <th scope="col" className="px-3 py-2.5 text-right">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {documents.map((doc) => {
                const cls = doc.latest_classification;
                const isExpanded = expandedClassificationId === doc.id;
                const isClassifying = classifyingId === doc.id;

                return (
                  <React.Fragment key={doc.id}>
                    <tr className="hover:bg-slate-50/70 transition-colors">
                      {/* Document info */}
                      <td className="px-4 py-2.5 align-top">
                        <div className="flex items-start gap-2">
                          <div className="pt-0.5">{getFileIcon(doc.mime_type)}</div>
                          <div className="min-w-0 max-w-xs">
                            <span
                              className="font-medium text-slate-800 truncate block text-xs"
                              title={doc.original_filename}
                            >
                              {doc.original_filename}
                            </span>
                            <div className="flex items-center gap-1.5 text-[10px] text-slate-400 mt-0.5">
                              <span className="font-mono bg-slate-100 px-1 py-0.2 rounded">
                                v{doc.document_version}
                              </span>
                              <span>•</span>
                              <span className="font-mono">{doc.file_extension}</span>
                              <span>•</span>
                              <span className="font-mono">{formatFileSize(doc.file_size_bytes)}</span>
                            </div>
                          </div>
                        </div>
                      </td>

                      {/* Declared Category */}
                      <td className="px-3 py-2.5 whitespace-nowrap align-top">
                        {getCategoryBadge(doc.document_category)}
                      </td>

                      {/* Classification & Prediction */}
                      <td className="px-3 py-2.5 align-top">
                        {cls ? (
                          <div className="space-y-1">
                            <div className="flex items-center gap-1.5 flex-wrap">
                              {getCategoryBadge(cls.predicted_category)}
                              {getClassificationStatusBadge(cls.status)}
                              <span className="font-mono text-[10px] font-semibold text-slate-500">
                                {Math.round(cls.confidence_score * 100)}%
                              </span>
                            </div>

                            {/* Declared vs Predicted Notice if mismatch */}
                            {cls.predicted_category !== doc.document_category && cls.status === 'CLASSIFIED' && (
                              <div className="text-[10px] text-amber-700 bg-amber-50/80 px-1.5 py-0.5 rounded border border-amber-200/60 inline-flex items-center gap-1">
                                <AlertTriangle className="w-2.5 h-2.5 text-amber-600 shrink-0" />
                                <span>Differs from declared category</span>
                              </div>
                            )}

                            {/* Toggle Evidence */}
                            <div>
                              <button
                                type="button"
                                onClick={() =>
                                  setExpandedClassificationId(isExpanded ? null : doc.id)
                                }
                                className="inline-flex items-center gap-1 text-[10px] font-medium text-sky-600 hover:text-sky-800 hover:underline pt-0.5"
                              >
                                {isExpanded ? (
                                  <>
                                    <ChevronDown className="w-3 h-3" />
                                    <span>Hide Evidence</span>
                                  </>
                                ) : (
                                  <>
                                    <ChevronRight className="w-3 h-3" />
                                    <span>View Evidence ({cls.evidence?.matched_headings?.length || 0} headings)</span>
                                  </>
                                )}
                              </button>
                            </div>
                          </div>
                        ) : (
                          <div className="flex items-center gap-1.5 text-slate-400 text-[11px] py-0.5">
                            <span className="italic">Not classified yet</span>
                          </div>
                        )}
                      </td>

                      {/* Actions */}
                      <td className="px-3 py-2.5 whitespace-nowrap text-right align-top space-x-1.5">
                        <button
                          type="button"
                          onClick={() => handleClassify(doc)}
                          disabled={isClassifying}
                          className="inline-flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium bg-sky-50 hover:bg-sky-100 text-sky-700 border border-sky-200 transition-colors disabled:opacity-50"
                          title="Run deterministic content classifier"
                        >
                          {isClassifying ? (
                            <Loader2 className="w-3 h-3 animate-spin text-sky-600" />
                          ) : (
                            <Sparkles className="w-3 h-3 text-sky-600" />
                          )}
                          <span>{cls ? 'Re-classify' : 'Classify'}</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDownload(doc)}
                          disabled={downloadingId === doc.id}
                          className="inline-flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium bg-white hover:bg-slate-100 text-slate-700 border border-slate-200 transition-colors disabled:opacity-50"
                          title="Download decrypted document"
                        >
                          {downloadingId === doc.id ? (
                            <Loader2 className="w-3 h-3 animate-spin text-slate-500" />
                          ) : (
                            <Download className="w-3 h-3 text-slate-600" />
                          )}
                          <span>Download</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDelete(doc)}
                          disabled={deletingId === doc.id}
                          className="inline-flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium bg-white hover:bg-rose-50 text-rose-600 border border-slate-200 hover:border-rose-200 transition-colors disabled:opacity-50"
                          title="Delete document"
                        >
                          {deletingId === doc.id ? (
                            <Loader2 className="w-3 h-3 animate-spin text-rose-500" />
                          ) : (
                            <Trash2 className="w-3 h-3" />
                          )}
                          <span>Delete</span>
                        </button>
                      </td>
                    </tr>

                    {/* Expandable Evidence Drawer */}
                    {isExpanded && cls && (
                      <tr className="bg-slate-50/70 border-t border-slate-100">
                        <td colSpan={4} className="px-4 py-3">
                          <div className="space-y-2.5 max-w-3xl">
                            {/* Evidence Header */}
                            <div className="flex items-center justify-between text-[11px] border-b border-slate-200/70 pb-1.5">
                              <span className="font-semibold text-slate-700 flex items-center gap-1.5">
                                <Sparkles className="w-3 h-3 text-sky-600" />
                                Explainable Classification Evidence (Engine v{cls.classifier_version})
                              </span>
                              <span className="text-slate-400 font-mono text-[10px]">
                                {new Date(cls.classified_at).toLocaleString()}
                              </span>
                            </div>

                            {/* Limitation Notice if any */}
                            {cls.limitation_code && (
                              <div className="p-2 rounded bg-amber-50 border border-amber-200 text-amber-800 text-[11px] space-y-0.5">
                                <span className="font-semibold">{cls.limitation_code}</span>: {cls.limitation_reason}
                              </div>
                            )}

                            {/* Signal Breakdown */}
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                              {/* Headings */}
                              <div className="space-y-1">
                                <span className="text-[10px] uppercase font-bold text-slate-500 tracking-wider">
                                  Matched Headings ({cls.evidence?.matched_headings?.length || 0})
                                </span>
                                {cls.evidence?.matched_headings && cls.evidence.matched_headings.length > 0 ? (
                                  <div className="flex flex-wrap gap-1">
                                    {cls.evidence.matched_headings.map((heading, i) => (
                                      <span
                                        key={i}
                                        className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-sky-100/70 text-sky-800 border border-sky-200/60"
                                      >
                                        {heading}
                                      </span>
                                    ))}
                                  </div>
                                ) : (
                                  <p className="text-[11px] text-slate-400 italic">No strong headings matched</p>
                                )}
                              </div>

                              {/* Keywords */}
                              <div className="space-y-1">
                                <span className="text-[10px] uppercase font-bold text-slate-500 tracking-wider">
                                  Matched Context Keywords ({cls.evidence?.matched_keywords?.length || 0})
                                </span>
                                {cls.evidence?.matched_keywords && cls.evidence.matched_keywords.length > 0 ? (
                                  <div className="flex flex-wrap gap-1">
                                    {cls.evidence.matched_keywords.map((kw, i) => (
                                      <span
                                        key={i}
                                        className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-slate-200/70 text-slate-700 border border-slate-300/60"
                                      >
                                        {kw}
                                      </span>
                                    ))}
                                  </div>
                                ) : (
                                  <p className="text-[11px] text-slate-400 italic">No context keywords matched</p>
                                )}
                              </div>
                            </div>

                            {/* Inspection Scope & Data Protection Note */}
                            <div className="text-[10px] text-slate-400 pt-1 flex items-center justify-between border-t border-slate-200/50">
                              <span>
                                Scope: {cls.evidence?.pages_inspected ?? 0} page(s) • {cls.evidence?.chars_inspected ?? 0} chars inspected
                              </span>
                              <span className="italic">
                                Deterministic dictionary signals only. No raw document text or sensitive numbers exposed.
                              </span>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};
