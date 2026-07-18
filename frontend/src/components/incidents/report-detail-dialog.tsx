import { useState } from 'react'
import { AlertTriangle, Loader2, Trash2 } from 'lucide-react'
import { toast } from 'sonner'

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { useDeleteReport, useReportDetail } from '@/api/queries'
import { ApiError } from '@/api/client'
import type { FieldMetadata } from '@/api/types'
import { confidenceKind, confidenceLabel } from '@/lib/confidence'

const FIELD_LABELS: Record<string, string> = {
  incident_title: 'Incident Title',
  incident_type: 'Incident Type',
  date: 'Date',
  operation_type: 'Operation Type',
  vessel_type: 'Vessel Type',
  vessel_information: 'Vessel Information',
  location: 'Location',
  weather_conditions: 'Weather Conditions',
  equipment_involved: 'Equipment Involved',
  sequence_of_events: 'Sequence of Events',
  immediate_causes: 'Immediate Causes',
  root_causes: 'Root Causes',
  casual_signature: 'Causal Signature',
  contributing_factors: 'Contributing Factors',
  human_factors: 'Human Factors',
  technical_failures: 'Technical Failures',
  environmental_factors: 'Environmental Factors',
  regulatory_issues: 'Regulatory Issues',
  injuries: 'Injuries',
  fatalities: 'Fatalities',
  pollution: 'Pollution',
  property_damage: 'Property Damage',
  lessons_learned: 'Lessons Learned',
  corrective_actions: 'Corrective Actions',
  safety_recommendations: 'Safety Recommendations',
  keywords: 'Keywords',
}

function renderValue(value: unknown) {
  if (value === null || value === undefined || value === '') {
    return <span className="text-muted-foreground italic">Not reported</span>
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-muted-foreground italic">Not reported</span>
    return (
      <ul className="list-disc space-y-1 pl-5">
        {value.map((v, i) => (
          <li key={i}>{String(v)}</li>
        ))}
      </ul>
    )
  }
  if (typeof value === 'object') {
    return (
      <ul className="list-disc space-y-1 pl-5">
        {Object.entries(value as Record<string, unknown>).map(([k, v]) => (
          <li key={k}>
            <span className="font-medium">{k}:</span> {String(v)}
          </li>
        ))}
      </ul>
    )
  }
  return <span>{String(value)}</span>
}

function FieldAccordionItem({ field }: { field: FieldMetadata }) {
  const reviewRequired = (field.human_revision_status ?? '').toLowerCase() === 'required'
  return (
    <AccordionItem value={field.field_name}>
      <AccordionTrigger>
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">
            {FIELD_LABELS[field.field_name] ?? field.field_name.replaceAll('_', ' ')}
          </span>
          <Badge variant={confidenceKind(field.confidence)} className="font-mono">
            {field.confidence !== null ? field.confidence.toFixed(2) : '—'}{' '}
            {confidenceLabel(field.confidence)}
          </Badge>
          {field.status && <Badge variant="secondary">{field.status}</Badge>}
          <Badge variant={reviewRequired ? 'warning' : 'success'}>
            {reviewRequired ? 'Review Required' : 'Verified'}
          </Badge>
        </div>
      </AccordionTrigger>
      <AccordionContent className="space-y-3 text-sm">
        {renderValue(field.value)}

        {field.reasoning && (
          <p className="text-muted-foreground">
            <span className="text-foreground font-medium">Extraction reasoning: </span>
            {field.reasoning}
          </p>
        )}

        {field.supporting_quotes.length > 0 && (
          <div>
            <p className="mb-1 text-xs font-semibold tracking-wide uppercase">Supporting quotes</p>
            <ul className="text-muted-foreground list-disc space-y-1 pl-5">
              {field.supporting_quotes.map((q, i) => (
                <li key={i} className="italic">
                  &ldquo;{q}&rdquo;
                </li>
              ))}
            </ul>
          </div>
        )}

        {field.source_page_numbers.length > 0 && (
          <p className="text-muted-foreground text-xs">
            <span className="font-medium">Source page(s): </span>
            {field.source_page_numbers.join(', ')}
          </p>
        )}
      </AccordionContent>
    </AccordionItem>
  )
}

export function ReportDetailDialog({
  reportId,
  onOpenChange,
}: {
  reportId: number | null
  onOpenChange: (open: boolean) => void
}) {
  const { data: report, isLoading } = useReportDetail(reportId)
  const deleteReport = useDeleteReport()
  const [confirmingDelete, setConfirmingDelete] = useState(false)

  function handleOpenChange(open: boolean) {
    if (!open) setConfirmingDelete(false)
    onOpenChange(open)
  }

  async function handleDelete() {
    if (reportId === null) return
    try {
      await deleteReport.mutateAsync(reportId)
      toast.success(`Report #${reportId} deleted.`)
      setConfirmingDelete(false)
      onOpenChange(false)
    } catch (err) {
      const message = err instanceof ApiError ? String(err.detail) : 'Could not delete report'
      toast.error(message)
    }
  }

  return (
    <Dialog open={reportId !== null} onOpenChange={handleOpenChange}>
      <DialogContent className="max-h-[85vh] max-w-3xl overflow-y-auto">
        {isLoading && (
          <div className="space-y-3">
            <Skeleton className="h-7 w-2/3" />
            <Skeleton className="h-4 w-1/3" />
            <Skeleton className="mt-4 h-40 w-full" />
          </div>
        )}

        {report && (
          <>
            <DialogHeader>
              <div className="flex items-start justify-between gap-4 pr-8">
                <DialogTitle className="font-display text-xl font-semibold">
                  {report.incident_title ?? `Report #${report.id}`}
                </DialogTitle>
                {!confirmingDelete ? (
                  <Button
                    variant="outline"
                    size="sm"
                    className="text-destructive hover:text-destructive shrink-0"
                    onClick={() => setConfirmingDelete(true)}
                  >
                    <Trash2 className="size-3.5" />
                    Delete
                  </Button>
                ) : (
                  <div className="flex shrink-0 items-center gap-2">
                    <Button variant="outline" size="sm" onClick={() => setConfirmingDelete(false)}>
                      Cancel
                    </Button>
                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={handleDelete}
                      disabled={deleteReport.isPending}
                    >
                      {deleteReport.isPending ? (
                        <Loader2 className="size-3.5 animate-spin" />
                      ) : (
                        <AlertTriangle className="size-3.5" />
                      )}
                      Confirm delete
                    </Button>
                  </div>
                )}
              </div>
              <div className="flex flex-wrap gap-1.5 pt-1">
                <Badge variant="secondary">{report.incident_type ?? 'Unclassified'}</Badge>
                <Badge variant={confidenceKind(report.overall_confidence)} className="font-mono">
                  {report.overall_confidence !== null ? report.overall_confidence.toFixed(2) : '—'}{' '}
                  {confidenceLabel(report.overall_confidence)}
                </Badge>
                <Badge variant={report.human_review_required ? 'warning' : 'success'}>
                  {report.human_review_required
                    ? `${report.fields_requiring_review.length} field(s) need review`
                    : 'No fields flagged for review'}
                </Badge>
              </div>
            </DialogHeader>

            <div className="grid grid-cols-2 gap-4 border-y py-4 sm:grid-cols-3">
              {[
                ['Date', report.incident_date ?? '—'],
                ['Location', report.location ?? '—'],
                ['Operation Type', report.operation_type ?? '—'],
                ['Vessel Type', report.vessel_type ?? '—'],
                ['Injuries', String(report.injuries)],
                ['Fatalities', String(report.fatalities)],
              ].map(([label, value]) => (
                <div key={label}>
                  <p className="text-muted-foreground text-[0.7rem] tracking-wide uppercase">{label}</p>
                  <p className="mt-0.5 truncate text-sm font-medium">{value}</p>
                </div>
              ))}
            </div>

            <Accordion type="multiple" className="max-h-[45vh] overflow-y-auto pr-1">
              {report.field_metadata.map((field) => (
                <FieldAccordionItem key={field.field_name} field={field} />
              ))}
            </Accordion>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
