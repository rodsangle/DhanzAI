import type { ReactNode } from "react";
import { SpaceShell } from "@/components/space/space-shell";

// S12 Space: one frame for the home and every page, so the tree stays put while you move between pages.
export default function Layout({ children }: { children: ReactNode }) {
  return <SpaceShell>{children}</SpaceShell>;
}
