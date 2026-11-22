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
  ChevronLeft,
  AlertTriangle,
  Info,
  FileSearch,
  Eye,
  X,
} from 'lucide-react';
import {
  VendorDocumentResponse,
  DocumentCategory,
  ClassificationStatus,
  ExtractionStatus,
  FieldStatus,
  ExtractedField,
  fetchVendorDocuments,
  uploadVendorDocument,
  downloadVendorDocument,
  deleteVendorDocument,
  classifyVendorDocument,
  extractVendorDocument,
  getDocumentPagePreviewUrl,
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
  const [extractingId, setExtractingId] = useState<string | null>(null);
  const [expandedExtractionId, setExpandedExtractionId] = useState<string | null>(null);

  // Original Document Page Preview Modal State
  const [pagePreview, setPagePreview] = useState<{
    documentId: string;
    documentName: string;
    pageNumber: number;
    fieldName?: string;
    field?: ExtractedField | null;
  } | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

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
      if (expandedExtractionId === doc.id) {
        setExpandedExtractionId(null);
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

  const handleExtract = async (doc: VendorDocumentResponse) => {
    setExtractingId(doc.id);
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      const result = await extractVendorDocument(vendorId, doc.id);
      setDocuments((prev) =>
        prev.map((d) => (d.id === doc.id ? { ...d, latest_extraction: result } : d))
      );
      setExpandedExtractionId(doc.id);
      setSuccessMessage(
        `Structured extraction complete for '${doc.original_filename}': ${result.status} (${result.extracted_fields_count} fields extracted)`
      );
      if (onActivityChange) onActivityChange();
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to extract document information');
    } finally {
      setExtractingId(null);
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

  const getExtractionStatusBadge = (status: ExtractionStatus) => {
    switch (status) {
      case 'COMPLETED':
        return (
          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            <CheckCircle2 className="w-2.5 h-2.5 text-emerald-600" />
            Completed
          </span>
        );
      case 'PARTIAL':
        return (
          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-amber-50 text-amber-700 border border-amber-200">
            <AlertTriangle className="w-2.5 h-2.5 text-amber-600" />
            Partial
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

  const getFieldStatusBadge = (status: FieldStatus) => {
    switch (status) {
      case 'EXTRACTED':
        return (
          <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            Extracted
          </span>
        );
      case 'MISSING':
        return (
          <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-semibold bg-slate-100 text-slate-500 border border-slate-200">
            Missing
          </span>
        );
      case 'UNREADABLE':
        return (
          <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-semibold bg-rose-50 text-rose-700 border border-rose-200">
            Unreadable
          </span>
        );
      case 'NEEDS_REVIEW':
        return (
          <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-semibold bg-amber-50 text-amber-700 border border-amber-200">
            Needs Review
          </span>
        );
      default:
        return null;
    }
  };

  const getQualityBadge = (field: ExtractedField) => {
    const score = field.quality_score ?? field.confidence;
    if (score === null || score === undefined || field.status === 'MISSING') {
      return null;
    }
    const pct = Math.round(score * 100);
    let colorClass = 'bg-emerald-50 text-emerald-800 border-emerald-200';
    if (pct < 50 || field.status === 'UNREADABLE') {
      colorClass = 'bg-rose-50 text-rose-800 border-rose-200';
    } else if (pct < 75 || field.status === 'NEEDS_REVIEW') {
      colorClass = 'bg-amber-50 text-amber-800 border-amber-200';
    }

    return (
      <span
        className={`inline-flex items-center px-1.5 py-0.2 rounded text-[10px] font-mono font-medium border ${colorClass} cursor-help`}
        title={`Evidence Quality Score: ${pct}%\n${field.quality_explanation || ''}`}
      >
        {pct}% Quality
      </span>
    );
  };

  const handleOpenPreview = (
    doc: VendorDocumentResponse,
    pageNumber: number = 1,
    fieldName?: string,
    field?: ExtractedField
  ) => {
    setPreviewError(null);
    setPreviewLoading(true);
    setPagePreview({
      documentId: doc.id,
      documentName: doc.original_filename,
      pageNumber: Math.max(1, pageNumber),
      fieldName,
      field,
    });
  };

  const formatFieldName = (name: string): string => {
    return name
      .split('_')
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
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
                <th scope="col" className="px-3 py-2.5">
                  Structured Information
                </th>
                <th scope="col" className="px-3 py-2.5 text-right">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {documents.map((doc) => {
                const cls = doc.latest_classification;
                const ext = doc.latest_extraction;
                const isExpanded = expandedClassificationId === doc.id;
                const isExtractionExpanded = expandedExtractionId === doc.id;
                const isClassifying = classifyingId === doc.id;
                const isExtracting = extractingId === doc.id;

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
                              <div className="inline-flex items-center gap-1 text-[10px] text-slate-500">
                                <span>Rule-based match score:</span>
                                <span className="font-mono font-bold text-slate-700 bg-slate-100 px-1 py-0.2 rounded border border-slate-200">
                                  {cls.confidence_score.toFixed(2)}
                                </span>
                                <div className="relative group inline-flex items-center">
                                  <Info className="w-2.5 h-2.5 text-slate-400 hover:text-slate-600 cursor-help" />
                                  <div className="hidden group-hover:block absolute z-30 left-1/2 -translate-x-1/2 bottom-full mb-1 w-64 p-2 bg-slate-900 text-white text-[10px] rounded shadow-lg pointer-events-none text-left">
                                    Rule-based heuristic match score [0.00–1.00] measuring matched signals. Not a statistical probability or proof of document authenticity.
                                  </div>
                                </div>
                              </div>
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

                      {/* Structured Information */}
                      <td className="px-3 py-2.5 align-top">
                        {ext ? (
                          <div className="space-y-1">
                            <div className="flex items-center gap-1.5 flex-wrap">
                              {getExtractionStatusBadge(ext.status)}
                              <span className="text-[10px] font-mono text-slate-600 bg-slate-100 px-1 py-0.2 rounded border border-slate-200">
                                {ext.extracted_fields_count} {ext.extracted_fields_count === 1 ? 'field' : 'fields'}
                              </span>
                            </div>
                            <div>
                              <button
                                type="button"
                                onClick={() =>
                                  setExpandedExtractionId(isExtractionExpanded ? null : doc.id)
                                }
                                className="inline-flex items-center gap-1 text-[10px] font-medium text-indigo-600 hover:text-indigo-800 hover:underline pt-0.5"
                              >
                                {isExtractionExpanded ? (
                                  <>
                                    <ChevronDown className="w-3 h-3" />
                                    <span>Hide Fields</span>
                                  </>
                                ) : (
                                  <>
                                    <ChevronRight className="w-3 h-3" />
                                    <span>View Fields ({ext.extracted_fields_count})</span>
                                  </>
                                )}
                              </button>
                            </div>
                          </div>
                        ) : (
                          <div className="flex items-center gap-1.5 text-slate-400 text-[11px] py-0.5">
                            <span className="italic">Not extracted yet</span>
                          </div>
                        )}
                      </td>

                      {/* Actions */}
                      <td className="px-3 py-2.5 whitespace-nowrap text-right align-top space-x-1.5">
                        <button
                          type="button"
                          onClick={() => handleExtract(doc)}
                          disabled={isExtracting}
                          className="inline-flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200 transition-colors disabled:opacity-50"
                          title="Run OCR and extract structured field values"
                        >
                          {isExtracting ? (
                            <Loader2 className="w-3 h-3 animate-spin text-indigo-600" />
                          ) : (
                            <FileSearch className="w-3 h-3 text-indigo-600" />
                          )}
                          <span>{ext ? 'Re-extract' : 'Extract'}</span>
                        </button>
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
                        <td colSpan={5} className="px-4 py-3">
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

                            {/* Score Explanation Banner */}
                            <div className="p-2 rounded bg-sky-50/70 border border-sky-100 text-sky-900 text-[11px] flex items-start gap-1.5">
                              <Info className="w-3.5 h-3.5 text-sky-600 shrink-0 mt-0.5" />
                              <div>
                                <span className="font-semibold">Rule-Based Match Score: {cls.confidence_score.toFixed(2)} / 1.00</span>
                                <p className="text-[10px] text-sky-700 mt-0.5">
                                  Heuristic match score reflecting keyword and heading signal weights matched in digital text. This is not a statistical probability, nor does it guarantee or imply document authenticity or legal validity.
                                </p>
                              </div>
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
                                Scope: {typeof cls.evidence?.text_length_chars === 'number' ? `${cls.evidence.text_length_chars} chars` : `${cls.evidence?.chars_inspected ?? 0} chars`} inspected
                              </span>
                              <span className="italic">
                                Deterministic dictionary signals only. No raw document text or sensitive identifiers exposed.
                              </span>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                    {/* Expandable Extraction Drawer */}
                    {isExtractionExpanded && ext && (
                      <tr className="bg-indigo-50/30 border-t border-indigo-100">
                        <td colSpan={5} className="px-4 py-3">
                          <div className="space-y-3 max-w-4xl">
                            <div className="flex items-center justify-between text-[11px] border-b border-indigo-200/70 pb-1.5">
                              <span className="font-semibold text-indigo-900 flex items-center gap-1.5">
                                <FileSearch className="w-3.5 h-3.5 text-indigo-600" />
                                Structured Information & Provenance (Schema: {CATEGORY_LABELS[ext.document_category_used as DocumentCategory] || ext.document_category_used} • OCR Engine v{ext.ocr_engine_version})
                              </span>
                              <span className="text-slate-400 font-mono text-[10px]">
                                {new Date(ext.extracted_at || ext.created_at || Date.now()).toLocaleString()}
                              </span>
                            </div>

                            {/* Limitation notice if any */}
                            {ext.limitation_reason && (
                              <div className="p-2 rounded bg-amber-50 border border-amber-200 text-amber-800 text-[11px] flex items-start gap-1.5">
                                <AlertTriangle className="w-3.5 h-3.5 text-amber-600 shrink-0 mt-0.5" />
                                <div>
                                  <span className="font-semibold">{ext.limitation_code || 'Notice'}:</span> {ext.limitation_reason}
                                </div>
                              </div>
                            )}

                            {/* Fields Table */}
                            <div className="bg-white rounded border border-slate-200 overflow-hidden shadow-xs">
                              <table className="min-w-full divide-y divide-slate-100 text-left text-xs">
                                <thead className="bg-slate-50 text-slate-500 font-medium text-[10px] uppercase tracking-wider">
                                  <tr>
                                    <th className="px-3 py-2">Field</th>
                                    <th className="px-3 py-2">Extracted Value</th>
                                    <th className="px-3 py-2">Status</th>
                                    <th className="px-3 py-2">Provenance & Evidence</th>
                                  </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-100 font-normal">
                                  {Object.entries(ext.fields).map(([fieldName, field]) => (
                                    <tr key={fieldName} className="hover:bg-slate-50/50">
                                      <td className="px-3 py-2 align-top font-medium text-slate-800 text-xs whitespace-nowrap">
                                        {formatFieldName(fieldName)}
                                      </td>
                                      <td className="px-3 py-2 align-top text-xs">
                                        {field.status === 'EXTRACTED' || field.status === 'NEEDS_REVIEW' ? (
                                          <div className="space-y-1">
                                            <div className="flex items-center gap-1.5 flex-wrap">
                                              <span className="font-mono text-slate-900 font-medium select-all">
                                                {field.masked_value || field.value}
                                              </span>
                                              {getQualityBadge(field)}
                                            </div>
                                            {field.normalization_notes && (
                                              <div className="text-[10px] text-amber-800 bg-amber-50/70 px-1.5 py-0.5 rounded border border-amber-200/50">
                                                <span className="font-semibold">Note:</span> {field.normalization_notes}
                                              </div>
                                            )}
                                          </div>
                                        ) : (
                                          <span className="text-slate-400 italic text-[11px]">
                                            {field.limitation_or_reason || (field.status === 'UNREADABLE' ? 'Unreadable text in document' : 'Field not present')}
                                          </span>
                                        )}
                                      </td>
                                      <td className="px-3 py-2 align-top whitespace-nowrap">
                                        {getFieldStatusBadge(field.status)}
                                      </td>
                                      <td className="px-3 py-2 align-top text-[11px] text-slate-600 space-y-1">
                                        {field.source ? (
                                          <>
                                            <div className="flex items-center gap-1.5 flex-wrap text-[10px]">
                                              {field.source.page_number && (
                                                <span className="font-semibold text-slate-700">
                                                  Page {field.source.page_number}
                                                </span>
                                              )}
                                              {field.source.extraction_method && (
                                                <>
                                                  <span>•</span>
                                                  <span className="font-mono bg-slate-100 text-slate-600 px-1 py-0.2 rounded border border-slate-200">
                                                    {field.source.extraction_method}
                                                  </span>
                                                </>
                                              )}
                                              {field.source.evidence_location && (
                                                <>
                                                  <span>•</span>
                                                  <span className="text-slate-500">{field.source.evidence_location}</span>
                                                </>
                                              )}
                                              {field.source.page_number && (
                                                <button
                                                  type="button"
                                                  onClick={() => handleOpenPreview(doc, field.source?.page_number || 1, fieldName, field)}
                                                  className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-sky-50 text-sky-700 hover:bg-sky-100 border border-sky-200 transition-colors ml-auto cursor-pointer"
                                                  title="Inspect evidence on original document page"
                                                >
                                                  <Eye className="w-3 h-3 text-sky-600" />
                                                  <span>Inspect Page</span>
                                                </button>
                                              )}
                                            </div>
                                            {field.source.evidence_snippet && (
                                              <div className="font-mono text-[10px] text-slate-600 bg-slate-50 p-1.5 rounded border border-slate-200/70 max-w-md truncate" title={field.source.evidence_snippet}>
                                                &ldquo;{field.source.evidence_snippet}&rdquo;
                                              </div>
                                            )}
                                          </>
                                        ) : (
                                          <span className="text-slate-400 italic text-[10px]">
                                            {field.limitation_or_reason || 'Field not detected in document content'}
                                          </span>
                                        )}
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>

                            <div className="text-[10px] text-slate-500 flex items-center justify-between border-t border-indigo-100/70 pt-2 flex-wrap gap-2">
                              <span>Deterministic field parsing & evidence quality scoring (Engine v{ext.extraction_engine_version || ext.ocr_engine_version || '2.0.0'}).</span>
                              <span className="font-medium text-amber-800 bg-amber-50 px-2 py-0.5 rounded border border-amber-200">
                                Evidence Inspection Only: Extracted data does not overwrite vendor records.
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

      {/* Original Document Evidence & Page Inspection Modal */}
      {pagePreview && (
        <div
          className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4 cursor-pointer"
          onClick={() => setPagePreview(null)}
          role="dialog"
          aria-modal="true"
        >
          <div
            className="bg-white rounded-xl shadow-2xl border border-slate-200 max-w-5xl w-full max-h-[92vh] flex flex-col overflow-hidden animate-in fade-in-0 duration-150 cursor-default"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="px-5 py-3.5 border-b border-slate-200 flex items-center justify-between bg-slate-50/80">
              <div className="flex items-center gap-2">
                <FileSearch className="w-4 h-4 text-sky-600" />
                <h3 className="text-sm font-bold text-slate-800">
                  Document Evidence & Original Page Inspection
                </h3>
                <span className="text-[11px] font-mono text-slate-500 bg-slate-200/70 px-2 py-0.5 rounded">
                  {pagePreview.documentName}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setPagePreview(null)}
                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium bg-slate-100 hover:bg-slate-200 text-slate-700 transition-colors cursor-pointer"
                >
                  <X className="w-3.5 h-3.5" />
                  <span>Close</span>
                </button>
              </div>
            </div>

            {/* Sub-header / Navigation */}
            <div className="px-5 py-2 border-b border-slate-200 bg-white flex items-center justify-between text-xs">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={pagePreview.pageNumber <= 1}
                  onClick={() => {
                    setPreviewLoading(true);
                    setPreviewError(null);
                    setPagePreview(prev => prev ? { ...prev, pageNumber: prev.pageNumber - 1 } : null);
                  }}
                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-semibold bg-slate-100 hover:bg-slate-200 text-slate-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer"
                >
                  <ChevronLeft className="w-3.5 h-3.5" />
                  <span>Previous Page</span>
                </button>
                <span className="font-semibold text-slate-700 text-xs px-2 py-1 bg-slate-50 rounded border border-slate-200">
                  Page {pagePreview.pageNumber}
                </span>
                <button
                  type="button"
                  onClick={() => {
                    setPreviewLoading(true);
                    setPreviewError(null);
                    setPagePreview(prev => prev ? { ...prev, pageNumber: prev.pageNumber + 1 } : null);
                  }}
                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-semibold bg-slate-100 hover:bg-slate-200 text-slate-700 transition-colors cursor-pointer"
                >
                  <span>Next Page</span>
                  <ChevronRight className="w-3.5 h-3.5" />
                </button>
              </div>

              {pagePreview.fieldName && (
                <div className="text-xs text-slate-600 flex items-center gap-1.5">
                  <span className="text-slate-400">Inspecting:</span>
                  <span className="font-semibold text-slate-800">{formatFieldName(pagePreview.fieldName)}</span>
                </div>
              )}
            </div>

            {/* Modal Body */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 p-5 overflow-y-auto max-h-[calc(92vh-140px)] bg-slate-50">
              {/* Left Column: Rendered Page Canvas */}
              <div className="lg:col-span-7 bg-white p-3 rounded-lg border border-slate-200 flex flex-col items-center justify-center min-h-[460px] relative shadow-xs">
                {previewLoading && (
                  <div className="absolute inset-0 bg-white/80 backdrop-blur-xs flex items-center justify-center z-10">
                    <div className="flex flex-col items-center gap-2">
                      <Loader2 className="w-6 h-6 animate-spin text-sky-600" />
                      <span className="text-xs text-slate-500 font-medium">Rendering page in memory...</span>
                    </div>
                  </div>
                )}
                {previewError ? (
                  <div className="p-4 text-center space-y-2">
                    <AlertTriangle className="w-8 h-8 text-amber-500 mx-auto" />
                    <p className="text-xs text-slate-700 font-medium">{previewError}</p>
                    <p className="text-[11px] text-slate-400">No further pages available in document.</p>
                  </div>
                ) : (
                  <img
                    src={getDocumentPagePreviewUrl(vendorId, pagePreview.documentId, pagePreview.pageNumber)}
                    alt={`Document Page ${pagePreview.pageNumber}`}
                    className="max-h-[580px] w-auto object-contain rounded border border-slate-200 shadow-sm select-none"
                    onLoad={() => setPreviewLoading(false)}
                    onError={() => {
                      setPreviewLoading(false);
                      setPreviewError("Page preview could not be loaded or page does not exist.");
                    }}
                  />
                )}
              </div>

              {/* Right Column: Evidence & Field Quality Details */}
              <div className="lg:col-span-5 space-y-3">
                {pagePreview.field ? (
                  <div className="bg-white p-4 rounded-lg border border-slate-200 shadow-xs space-y-3">
                    <div className="flex items-center justify-between border-b border-slate-100 pb-2">
                      <h4 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                        {formatFieldName(pagePreview.fieldName || 'Field Evidence')}
                      </h4>
                      {getFieldStatusBadge(pagePreview.field.status)}
                    </div>

                    <div>
                      <span className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">
                        Extracted Value (Masked)
                      </span>
                      <div className="font-mono text-sm bg-slate-50 p-2 rounded-md border border-slate-200 text-slate-900 font-bold select-all">
                        {pagePreview.field.masked_value || pagePreview.field.value || 'None'}
                      </div>
                    </div>

                    {/* Quality Assessment Card */}
                    <div className="p-2.5 rounded-md bg-indigo-50/50 border border-indigo-100 space-y-1.5">
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-semibold text-indigo-900">Evidence Quality</span>
                        {getQualityBadge(pagePreview.field)}
                      </div>
                      {pagePreview.field.quality_explanation && (
                        <p className="text-[11px] text-slate-600">
                          {pagePreview.field.quality_explanation}
                        </p>
                      )}
                      {pagePreview.field.quality_breakdown && (
                        <div className="grid grid-cols-2 gap-1 text-[10px] font-mono text-slate-500 pt-1 border-t border-indigo-100/60">
                          <div>Source Fidelity: {Math.round(pagePreview.field.quality_breakdown.source_quality * 100)}%</div>
                          <div>Label Match: {Math.round(pagePreview.field.quality_breakdown.label_match * 100)}%</div>
                          <div>Format Valid: {Math.round(pagePreview.field.quality_breakdown.format_validity * 100)}%</div>
                          <div>Normalization: {Math.round(pagePreview.field.quality_breakdown.normalization_adjustment * 100)}%</div>
                        </div>
                      )}
                    </div>

                    {/* Normalization Note */}
                    {pagePreview.field.normalization_notes && (
                      <div className="p-2 rounded-md bg-amber-50 border border-amber-200 text-amber-800 text-xs">
                        <span className="font-semibold">Normalization Note:</span> {pagePreview.field.normalization_notes}
                      </div>
                    )}

                    {/* Source Evidence */}
                    <div>
                      <span className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">
                        Source Evidence Snippet
                      </span>
                      <div className="font-mono text-[11px] text-slate-700 bg-slate-50 p-2.5 rounded-md border border-slate-200 whitespace-pre-wrap">
                        &ldquo;{pagePreview.field.source?.evidence_snippet || 'No snippet available'}&rdquo;
                      </div>
                      {pagePreview.field.source?.evidence_location && (
                        <span className="block text-[10px] text-slate-500 mt-1">
                          Location: {pagePreview.field.source.evidence_location}
                        </span>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="bg-white p-4 rounded-lg border border-slate-200 text-center text-xs text-slate-500">
                    Select a field from the extraction table to view specific evidence details.
                  </div>
                )}

                {/* Strict Compliance Non-Mutation Notice */}
                <div className="p-3 rounded-lg bg-slate-100 border border-slate-200 text-[11px] text-slate-600 space-y-1">
                  <div className="flex items-center gap-1.5 font-semibold text-slate-700">
                    <Shield className="w-3.5 h-3.5 text-sky-600 shrink-0" />
                    <span>Evidence-Only Principle</span>
                  </div>
                  <p className="text-[10px] text-slate-500 leading-relaxed">
                    Extracted values are structured evidence for operator review. Extraction never alters vendor-submitted fields, mutates approval status, or overwrites database records.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
