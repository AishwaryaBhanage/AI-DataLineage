import { Download, X, Check } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { toast } from 'sonner'

interface Props {
  original: string
  corrected: string
}

export function SqlDiff({ original, corrected }: Props) {
  const handleDownload = () => {
    const blob = new Blob([corrected], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'corrected_model.sql'
    a.click()
    URL.revokeObjectURL(url)
    toast.success('Downloaded corrected SQL')
  }

  const handleCopy = () => {
    navigator.clipboard.writeText(corrected)
    toast.success('Copied to clipboard')
  }

  return (
    <div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Original */}
        <div>
          <div className="flex items-center gap-2 mb-2">
            <div className="w-5 h-5 rounded bg-rose-100 text-rose-600 flex items-center justify-center">
              <X className="w-3 h-3" />
            </div>
            <span className="text-[11px] font-bold text-rose-600 uppercase tracking-wider">
              Original (broken)
            </span>
          </div>
          <pre className="max-h-[320px] overflow-auto">{original}</pre>
        </div>

        {/* Corrected */}
        <div>
          <div className="flex items-center gap-2 mb-2">
            <div className="w-5 h-5 rounded bg-emerald-100 text-emerald-600 flex items-center justify-center">
              <Check className="w-3 h-3" />
            </div>
            <span className="text-[11px] font-bold text-emerald-600 uppercase tracking-wider">
              Corrected
            </span>
          </div>
          <pre className="max-h-[320px] overflow-auto border-emerald-200 bg-emerald-50/30">
            {corrected}
          </pre>
        </div>
      </div>

      <div className="flex gap-2 mt-4">
        <Button variant="secondary" size="sm" onClick={handleCopy}>
          <Check className="w-3.5 h-3.5" /> Copy
        </Button>
        <Button variant="primary" size="sm" onClick={handleDownload}>
          <Download className="w-3.5 h-3.5" /> Download corrected SQL
        </Button>
      </div>
    </div>
  )
}
