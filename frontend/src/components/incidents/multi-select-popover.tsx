import { ChevronDown } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'

export function MultiSelectPopover({
  label,
  options,
  selected,
  onChange,
}: {
  label: string
  options: string[]
  selected: string[]
  onChange: (values: string[]) => void
}) {
  function toggle(value: string) {
    onChange(selected.includes(value) ? selected.filter((v) => v !== value) : [...selected, value])
  }

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="justify-between font-normal">
          <span className="flex items-center gap-1.5">
            {label}
            {selected.length > 0 && (
              <Badge variant="secondary" className="rounded-full px-1.5 font-mono text-[0.65rem]">
                {selected.length}
              </Badge>
            )}
          </span>
          <ChevronDown className="text-muted-foreground size-3.5" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-64 p-0" align="start">
        {/* A plain max-height + overflow-y-auto div, not ScrollArea: Radix's
            ScrollArea Viewport sizes itself with height:100%, which only
            resolves against an ancestor with a *definite* height -- a
            max-height alone doesn't count, so the viewport was rendering at
            its full natural content height instead of clipping/scrolling,
            and a long option list (e.g. every distinct causal_signature
            value) would balloon the whole popover open uncapped. */}
        <div className="max-h-64 overflow-y-auto p-2">
          {options.length === 0 && (
            <p className="text-muted-foreground px-2 py-3 text-center text-xs">No values yet</p>
          )}
          {options.map((option) => (
            <label
              key={option}
              className="hover:bg-accent/10 flex cursor-pointer items-center gap-2.5 rounded-md px-2 py-1.5 text-sm"
            >
              <Checkbox checked={selected.includes(option)} onCheckedChange={() => toggle(option)} />
              <span className="truncate">{option}</span>
            </label>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  )
}
