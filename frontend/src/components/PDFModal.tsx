import { getPdfUrl } from '../api/invoices'

interface Props {
  invoiceId: number
  filename: string | null
  onClose: () => void
}

function isImageFile(filename: string | null): boolean {
  if (!filename) return false
  return /\.(jpe?g|png)$/i.test(filename)
}

export default function PDFModal({ invoiceId, filename, onClose }: Props) {
  const url = getPdfUrl(invoiceId)
  const isImage = isImageFile(filename)

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="bg-white rounded-xl shadow-2xl flex flex-col w-[90vw] h-[90vh] overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
          <span className="font-medium text-gray-800 text-sm truncate">
            {filename || 'Příloha'}
          </span>
          <div className="flex gap-2">
            <a
              href={url}
              download={filename || 'priloha'}
              className="px-3 py-1.5 text-xs bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
            >
              {isImage ? 'Stáhnout' : 'Stáhnout PDF'}
            </a>
            <button
              onClick={onClose}
              className="px-3 py-1.5 text-xs text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
            >
              Zavřít
            </button>
          </div>
        </div>

        {/* Preview */}
        <div className="flex-1 bg-gray-100 overflow-auto flex items-center justify-center">
          {isImage ? (
            <img
              src={url}
              alt={filename || 'příloha'}
              className="max-w-full max-h-full object-contain"
            />
          ) : (
            <iframe
              src={url}
              className="pdf-iframe w-full h-full"
              title="Náhled faktury"
            />
          )}
        </div>
      </div>
    </div>
  )
}
