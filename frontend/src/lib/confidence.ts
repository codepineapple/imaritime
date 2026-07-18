export type ConfidenceKind = 'success' | 'warning' | 'destructive' | 'secondary'

export function confidenceKind(confidence: number | null): ConfidenceKind {
  if (confidence === null) return 'secondary'
  if (confidence >= 0.8) return 'success'
  if (confidence >= 0.5) return 'warning'
  return 'destructive'
}

export function confidenceLabel(confidence: number | null): string {
  if (confidence === null) return 'Unknown'
  if (confidence >= 0.8) return 'High'
  if (confidence >= 0.5) return 'Medium'
  return 'Low'
}
