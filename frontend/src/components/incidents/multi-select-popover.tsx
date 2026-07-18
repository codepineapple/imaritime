import { ChevronDown } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'

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
        <ScrollArea className="max-h-64">
          <div className="p-2">
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
        </ScrollArea>
      </PopoverContent>
    </Popover>
  )
}
