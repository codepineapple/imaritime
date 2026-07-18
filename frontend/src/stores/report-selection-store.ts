import { create } from 'zustand'

interface ReportSelectionState {
  selectedIds: number[]
  toggle: (id: number) => void
  /** Replaces the whole selection -- used by "select all" / "clear all" on the current page. */
  setSelected: (ids: number[]) => void
  clear: () => void
  isSelected: (id: number) => boolean
}

export const useReportSelectionStore = create<ReportSelectionState>((set, get) => ({
  selectedIds: [],
  toggle: (id) =>
    set((state) => ({
      selectedIds: state.selectedIds.includes(id)
        ? state.selectedIds.filter((i) => i !== id)
        : [...state.selectedIds, id],
    })),
  setSelected: (ids) => set({ selectedIds: ids }),
  clear: () => set({ selectedIds: [] }),
  isSelected: (id) => get().selectedIds.includes(id),
}))
