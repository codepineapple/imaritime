import { useState } from 'react'
import { Search, X } from 'lucide-react'

import { useSearchSuggestions } from '@/api/queries'
import type { SearchToken } from '@/api/types'
import { cn } from '@/lib/utils'

const FIELD_LABELS: Record<string, string> = {
  all: 'All Fields',
  incident_title: 'Title',
  incident_type: 'Incident Type',
  location: 'Location',
  operation_type: 'Operation Type',
  vessel_type: 'Vessel Type',
  casual_signature: 'Causal Signature',
  vessel_information: 'Vessel Info',
  equipment_involved: 'Equipment',
  sequence_of_events: 'Sequence of Events',
  immediate_causes: 'Immediate Causes',
  root_causes: 'Root Causes',
  contributing_factors: 'Contributing Factors',
  human_factors: 'Human Factors',
  technical_failures: 'Technical Failures',
  regulatory_issues: 'Regulatory Issues',
  lessons_learned: 'Lessons Learned',
  corrective_actions: 'Corrective Actions',
  safety_recommendations: 'Safety Recs',
  keywords: 'Keywords',
}

function fieldLabel(field: string): string {
  return FIELD_LABELS[field] ?? field.replaceAll('_', ' ')
}

export function SearchBar({
  tokens,
  onTokensChange,
}: {
  tokens: SearchToken[]
  onTokensChange: (tokens: SearchToken[]) => void
}) {
  const [value, setValue] = useState('')
  const { data: suggestions } = useSearchSuggestions(value)

  function addToken(token: SearchToken) {
    const exists = tokens.some((t) => t.field === token.field && t.text === token.text)
    if (!exists) onTokensChange([...tokens, token])
    setValue('')
  }

  function removeToken(index: number) {
    onTokensChange(tokens.filter((_, i) => i !== index))
  }

  return (
    <div className="relative">
      {tokens.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-1.5">
          {tokens.map((token, i) => (
            <span
              key={`${token.field}-${token.text}-${i}`}
              className="bg-accent/15 text-accent-foreground border-accent/30 inline-flex items-center gap-1.5 rounded-full border py-1 pr-1.5 pl-3 text-xs font-medium"
            >
              <span className="text-accent-foreground/70 font-mono text-[0.65rem] tracking-wide uppercase">
                {fieldLabel(token.field)}
              </span>
              <span>&ldquo;{token.text}&rdquo;</span>
              <button
                onClick={() => removeToken(i)}
                className="hover:bg-accent/30 rounded-full p-0.5"
                aria-label="Remove filter"
              >
                <X className="size-3" />
              </button>
            </span>
          ))}
        </div>
      )}

      <div className="relative">
        <Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2" />
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && value.trim()) {
              e.preventDefault()
              addToken({ field: 'all', text: value.trim() })
            }
          }}
          placeholder="Search any field — root causes, lessons learned, operation type, vessel type…"
          className="border-input bg-card focus-visible:ring-ring/50 focus-visible:border-ring h-11 w-full rounded-full border pr-4 pl-10 text-sm shadow-xs outline-none focus-visible:ring-[3px]"
        />
      </div>

      {value.trim().length >= 2 && (
        <div className="bg-popover absolute z-20 mt-1.5 w-full overflow-hidden rounded-lg border shadow-md">
          {suggestions && suggestions.length > 0 ? (
            <ul className="max-h-72 overflow-y-auto py-1">
              {suggestions.map((s, i) => (
                <li key={i}>
                  <button
                    onClick={() => addToken(s)}
                    className={cn(
                      'flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm',
                      'hover:bg-accent/10',
                    )}
                  >
                    <span className="bg-accent/15 text-accent-foreground shrink-0 rounded-full px-2 py-0.5 font-mono text-[0.65rem] font-semibold tracking-wide uppercase">
                      {fieldLabel(s.field)}
                    </span>
                    <span className="truncate">{s.text}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted-foreground px-3 py-2.5 text-sm">
              No matching values — press Enter to search all fields by keyword and
              meaning (semantic search).
            </p>
          )}
        </div>
      )}
    </div>
  )
}
