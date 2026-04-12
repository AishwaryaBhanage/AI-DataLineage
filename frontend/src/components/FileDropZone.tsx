import { useState, useRef, DragEvent, ChangeEvent } from 'react'
import { Upload, FileJson, X, CheckCircle2 } from 'lucide-react'
import { cn } from '@/lib/utils'

// Reusable drag-and-drop file input.
//
// - Accepts drag-drop OR click-to-browse
// - Validates file type against `accept` (e.g. 'application/json')
// - Shows selected file name + size
// - Calls onFileSelect(file | null)

interface Props {
  label: string
  hint?: string
  accept?: string
  file: File | null
  onFileSelect: (file: File | null) => void
  /** Max size in MB; default 50 */
  maxSizeMb?: number
  /** Optional — shows ✓ badge when already uploaded to server */
  uploaded?: boolean
}

export function FileDropZone({
  label,
  hint,
  accept = 'application/json,.json',
  file,
  onFileSelect,
  maxSizeMb = 50,
  uploaded = false,
}: Props) {
  const [isDragging, setIsDragging] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleFile = (f: File | null) => {
    setError(null)
    if (!f) {
      onFileSelect(null)
      return
    }
    if (maxSizeMb && f.size > maxSizeMb * 1024 * 1024) {
      setError(`File too large (${(f.size / 1024 / 1024).toFixed(1)} MB). Max: ${maxSizeMb} MB`)
      return
    }
    onFileSelect(f)
  }

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragging(true)
  }

  const handleDragLeave = () => setIsDragging(false)

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragging(false)
    const dropped = e.dataTransfer.files?.[0]
    if (dropped) handleFile(dropped)
  }

  const handleChange = (e: ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0]
    if (selected) handleFile(selected)
  }

  const clear = () => {
    setError(null)
    onFileSelect(null)
    if (inputRef.current) inputRef.current.value = ''
  }

  return (
    <div>
      <div className="text-[12px] font-semibold text-slate-600 uppercase tracking-wider mb-1.5">
        {label}
      </div>

      {file ? (
        // Selected state
        <div
          className={cn(
            'flex items-center gap-3 px-4 py-3 rounded-lg border-2',
            uploaded
              ? 'bg-emerald-50 border-emerald-200'
              : 'bg-brand-50 border-brand-200',
          )}
        >
          <div
            className={cn(
              'w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0',
              uploaded
                ? 'bg-emerald-100 text-emerald-700'
                : 'bg-white text-brand-600',
            )}
          >
            {uploaded ? (
              <CheckCircle2 className="w-5 h-5" />
            ) : (
              <FileJson className="w-5 h-5" />
            )}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[13px] font-semibold text-slate-900 truncate">
              {file.name}
            </div>
            <div className="text-[11px] text-slate-500">
              {(file.size / 1024).toFixed(1)} KB
              {uploaded && ' · uploaded'}
            </div>
          </div>
          <button
            type="button"
            onClick={clear}
            className="w-8 h-8 rounded-lg hover:bg-white flex items-center justify-center text-slate-400 hover:text-slate-600 flex-shrink-0"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      ) : (
        // Empty state — drop zone
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => inputRef.current?.click()}
          className={cn(
            'flex flex-col items-center justify-center gap-2 px-5 py-6 rounded-lg border-2 border-dashed cursor-pointer transition-colors',
            isDragging
              ? 'border-brand-500 bg-brand-50'
              : 'border-slate-200 bg-slate-50 hover:border-slate-300 hover:bg-slate-100/50',
          )}
        >
          <div className="w-10 h-10 rounded-lg bg-white shadow-sm flex items-center justify-center text-slate-400">
            <Upload className="w-4 h-4" />
          </div>
          <div className="text-center">
            <div className="text-[13px] font-semibold text-slate-700">
              Drop file here or click to browse
            </div>
            {hint && (
              <div className="text-[11px] text-slate-500 mt-0.5">{hint}</div>
            )}
          </div>
        </div>
      )}

      <input
        ref={inputRef}
        type="file"
        accept={accept}
        onChange={handleChange}
        className="hidden"
      />

      {error && (
        <div className="mt-1.5 text-[11px] text-rose-600 font-medium">
          {error}
        </div>
      )}
    </div>
  )
}
