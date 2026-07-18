import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Slider } from '@/components/ui/slider'
import { useVocab } from '@/api/queries'
import { MultiSelectPopover } from '@/components/incidents/multi-select-popover'

export interface SecondaryFilters {
  dateFrom: string
  dateTo: string
  minInjuries: string
  minFatalities: string
  confidenceRange: [number, number]
  humanReview: 'any' | 'required' | 'not_required'
  hasDataIn: string[]
  operationTypes: string[]
  vesselTypes: string[]
  casualSignatures: string[]
}

export const DEFAULT_SECONDARY_FILTERS: SecondaryFilters = {
  dateFrom: '',
  dateTo: '',
  minInjuries: '',
  minFatalities: '',
  confidenceRange: [0, 1],
  humanReview: 'any',
  hasDataIn: [],
  operationTypes: [],
  vesselTypes: [],
  casualSignatures: [],
}

const HAS_DATA_OPTIONS = [
  { value: 'human_factors', label: 'Human Factors' },
  { value: 'technical_failures', label: 'Technical Failures' },
  { value: 'contributing_factors', label: 'Contributing Factors' },
  { value: 'regulatory_issues', label: 'Regulatory Issues' },
]

export function FiltersPanel({
  filters,
  onChange,
  onApply,
  onReset,
}: {
  filters: SecondaryFilters
  onChange: (filters: SecondaryFilters) => void
  onApply: () => void
  onReset: () => void
}) {
  const { data: vocab } = useVocab()

  function set<K extends keyof SecondaryFilters>(key: K, value: SecondaryFilters[K]) {
    onChange({ ...filters, [key]: value })
  }

  return (
    <div className="bg-card space-y-5 rounded-lg border p-5">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <div className="space-y-1.5">
          <Label className="text-muted-foreground text-xs tracking-wide uppercase">Date From</Label>
          <Input type="date" value={filters.dateFrom} onChange={(e) => set('dateFrom', e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label className="text-muted-foreground text-xs tracking-wide uppercase">Date To</Label>
          <Input type="date" value={filters.dateTo} onChange={(e) => set('dateTo', e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label className="text-muted-foreground text-xs tracking-wide uppercase">Min. Injuries</Label>
          <Input
            type="number"
            min={0}
            value={filters.minInjuries}
            onChange={(e) => set('minInjuries', e.target.value)}
            placeholder="0"
          />
        </div>
        <div className="space-y-1.5">
          <Label className="text-muted-foreground text-xs tracking-wide uppercase">Min. Fatalities</Label>
          <Input
            type="number"
            min={0}
            value={filters.minFatalities}
            onChange={(e) => set('minFatalities', e.target.value)}
            placeholder="0"
          />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 border-t pt-5 lg:grid-cols-3">
        <div className="space-y-2.5">
          <Label className="text-muted-foreground text-xs tracking-wide uppercase">
            Confidence Range
          </Label>
          <div className="px-1">
            <Slider
              min={0}
              max={1}
              step={0.05}
              value={filters.confidenceRange}
              onValueChange={(v) => set('confidenceRange', v as [number, number])}
            />
            <div className="text-muted-foreground mt-1.5 flex justify-between font-mono text-xs tabular-nums">
              <span>{filters.confidenceRange[0].toFixed(2)}</span>
              <span>{filters.confidenceRange[1].toFixed(2)}</span>
            </div>
          </div>
        </div>

        <div className="space-y-2.5">
          <Label className="text-muted-foreground text-xs tracking-wide uppercase">Human Review</Label>
          <RadioGroup
            value={filters.humanReview}
            onValueChange={(v) => set('humanReview', v as SecondaryFilters['humanReview'])}
            className="grid grid-cols-3 gap-2"
          >
            {(['any', 'required', 'not_required'] as const).map((v) => (
              <label key={v} className="flex items-center gap-1.5 text-sm">
                <RadioGroupItem value={v} />
                {v === 'any' ? 'Any' : v === 'required' ? 'Required' : 'Not required'}
              </label>
            ))}
          </RadioGroup>
        </div>

        <div className="space-y-2.5">
          <Label className="text-muted-foreground text-xs tracking-wide uppercase">Has Data In</Label>
          <div className="grid grid-cols-2 gap-1.5">
            {HAS_DATA_OPTIONS.map((opt) => (
              <label key={opt.value} className="flex items-center gap-1.5 text-sm">
                <Checkbox
                  checked={filters.hasDataIn.includes(opt.value)}
                  onCheckedChange={(checked) =>
                    set(
                      'hasDataIn',
                      checked
                        ? [...filters.hasDataIn, opt.value]
                        : filters.hasDataIn.filter((v) => v !== opt.value),
                    )
                  }
                />
                {opt.label}
              </label>
            ))}
          </div>
        </div>
      </div>

      <div className="flex flex-wrap items-end justify-between gap-4 border-t pt-5">
        <div className="flex flex-wrap gap-2.5">
          <MultiSelectPopover
            label="Operation Type"
            options={vocab?.operation_type ?? []}
            selected={filters.operationTypes}
            onChange={(v) => set('operationTypes', v)}
          />
          <MultiSelectPopover
            label="Vessel Type"
            options={vocab?.vessel_type ?? []}
            selected={filters.vesselTypes}
            onChange={(v) => set('vesselTypes', v)}
          />
          <MultiSelectPopover
            label="Causal Signature"
            options={vocab?.casual_signature ?? []}
            selected={filters.casualSignatures}
            onChange={(v) => set('casualSignatures', v)}
          />
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={onReset}>
            Reset
          </Button>
          <Button onClick={onApply}>Apply Filters</Button>
        </div>
      </div>
    </div>
  )
}
