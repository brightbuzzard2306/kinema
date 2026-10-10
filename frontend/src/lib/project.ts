"use client";

import { useSyncExternalStore } from "react";

/** State of the "Project" dialog (About / Team tabs). A tiny external store so any button can open it without prop-drilling. */
export type ProjectTab = "about" | "team";
interface ProjectState {
  open: boolean;
  tab: ProjectTab;
}

let state: ProjectState = { open: false, tab: "about" };
const listeners = new Set<() => void>();
const set = (next: ProjectState) => {
  state = next;
  listeners.forEach((l) => l());
};

export const openProject = (tab: ProjectTab = "about") => set({ open: true, tab });
export const closeProject = () => set({ ...state, open: false });
export const setProjectTab = (tab: ProjectTab) => set({ ...state, tab });

const subscribe = (cb: () => void) => {
  listeners.add(cb);
  return () => listeners.delete(cb);
};
export const useProject = (): ProjectState => useSyncExternalStore(subscribe, () => state, () => state);
