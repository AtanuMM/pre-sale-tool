import { useRef, useState } from 'react'
import { UploadIcon } from 'lucide-react'

import type { ProjectIntakeLimits } from '@/api/projects'
import { Button } from '@/components/ui/button'
import { formatBytes, validateSelectedFiles } from '@/lib/validateIntakeFiles'
import { cn } from '@/lib/utils'

type FileDropzoneProps = {
  limits: ProjectIntakeLimits
  files: File[]
  onChange: (files: File[]) => void
  disabled?: boolean
}

export function FileDropzone({ limits, files, onChange, disabled }: FileDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)
  const accept = limits.allowed_extensions.map((e) => `.${e}`).join(',')

  const mergeFiles = (incoming: FileList | File[]) => {
    const combined = [...files, ...Array.from(incoming)]
    const { valid, issues } = validateSelectedFiles(combined, limits)
    onChange(valid)
    return issues
  }

  return (
    <div className="space-y-3">
      <div
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') inputRef.current?.click()
        }}
        onDragOver={(e) => {
          e.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragOver(false)
          if (disabled) return
          mergeFiles(e.dataTransfer.files)
        }}
        className={cn(
          'flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border bg-muted/30 px-4 py-8 text-center transition-colors',
          dragOver && 'border-primary bg-muted/50',
          disabled && 'opacity-60',
        )}
      >
        <UploadIcon className="size-8 text-muted-foreground" aria-hidden />
        <p className="text-sm text-muted-foreground">
          Drag and drop files here, or{' '}
          <Button
            type="button"
            variant="link"
            className="h-auto p-0"
            disabled={disabled}
            onClick={() => inputRef.current?.click()}
          >
            browse
          </Button>
        </p>
        <p className="text-xs text-muted-foreground">
          Up to {limits.max_files_per_input} files, {formatBytes(limits.max_file_bytes)} each (
          {limits.allowed_extensions.join(', ')})
        </p>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={accept}
          className="sr-only"
          disabled={disabled}
          onChange={(e) => {
            if (e.target.files) mergeFiles(e.target.files)
            e.target.value = ''
          }}
        />
      </div>
      {files.length > 0 ? (
        <ul className="space-y-2">
          {files.map((file) => (
            <li
              key={`${file.name}-${file.size}-${file.lastModified}`}
              className="flex items-center justify-between gap-2 rounded-md border border-border px-3 py-2 text-sm"
            >
              <span className="min-w-0 truncate">{file.name}</span>
              <span className="shrink-0 text-muted-foreground">{formatBytes(file.size)}</span>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={disabled}
                onClick={() => onChange(files.filter((f) => f !== file))}
              >
                Remove
              </Button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
