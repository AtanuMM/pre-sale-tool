import type { InputKind, ProjectIntakeLimits } from '@/api/projects'
import { FileDropzone } from '@/components/projects/FileDropzone'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { INPUT_KIND_OPTIONS } from '@/lib/projectLabels'

export type IntakeFieldsState = {
  kind: InputKind
  receivedAtLocal: string
  receivedFrom: string
  subject: string
  body: string
  files: File[]
}

type IntakeFieldsProps = {
  limits: ProjectIntakeLimits
  value: IntakeFieldsState
  onChange: (next: IntakeFieldsState) => void
  disabled?: boolean
  showAttachments?: boolean
  fileIssues?: string[]
}

export function IntakeFields({
  limits,
  value,
  onChange,
  disabled,
  showAttachments = true,
  fileIssues = [],
}: IntakeFieldsProps) {
  const patch = (partial: Partial<IntakeFieldsState>) => onChange({ ...value, ...partial })

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2 sm:col-span-2">
          <Label htmlFor="intake-kind">Source type</Label>
          <Select
            value={value.kind}
            onValueChange={(v) => patch({ kind: v as InputKind })}
            disabled={disabled}
          >
            <SelectTrigger id="intake-kind">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {INPUT_KIND_OPTIONS.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <Label htmlFor="intake-received">Received at</Label>
          <Input
            id="intake-received"
            type="datetime-local"
            value={value.receivedAtLocal}
            onChange={(e) => patch({ receivedAtLocal: e.target.value })}
            disabled={disabled}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="intake-from">Received from</Label>
          <Input
            id="intake-from"
            value={value.receivedFrom}
            onChange={(e) => patch({ receivedFrom: e.target.value })}
            disabled={disabled}
            placeholder="client@example.com"
          />
        </div>
        <div className="space-y-2 sm:col-span-2">
          <Label htmlFor="intake-subject">Subject</Label>
          <Input
            id="intake-subject"
            value={value.subject}
            onChange={(e) => patch({ subject: e.target.value })}
            disabled={disabled}
          />
        </div>
        <div className="space-y-2 sm:col-span-2">
          <Label htmlFor="intake-body">Body</Label>
          <Textarea
            id="intake-body"
            value={value.body}
            onChange={(e) => patch({ body: e.target.value })}
            disabled={disabled}
            rows={8}
            className="min-h-[160px]"
          />
        </div>
      </div>
      {showAttachments ? (
        <div className="space-y-2">
          <Label>Attachments</Label>
          <FileDropzone
            limits={limits}
            files={value.files}
            onChange={(files) => patch({ files })}
            disabled={disabled}
          />
          {fileIssues.map((msg) => (
            <p key={msg} className="text-sm text-destructive">
              {msg}
            </p>
          ))}
        </div>
      ) : null}
    </div>
  )
}
