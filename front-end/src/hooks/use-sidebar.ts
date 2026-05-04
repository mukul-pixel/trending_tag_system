import { useEffect, useState } from "react";

const KEY = "sc-sidebar-collapsed";
const EVT = "sc-sidebar-change";

export function useSidebarCollapsed() {
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return window.localStorage.getItem(KEY) === "1";
  });

  useEffect(() => {
    const handler = (e: Event) => {
      const v = (e as CustomEvent<boolean>).detail;
      setCollapsed(v);
    };
    window.addEventListener(EVT, handler as EventListener);
    return () => window.removeEventListener(EVT, handler as EventListener);
  }, []);

  const toggle = () => {
    const next = !collapsed;
    window.localStorage.setItem(KEY, next ? "1" : "0");
    window.dispatchEvent(new CustomEvent(EVT, { detail: next }));
    setCollapsed(next);
  };

  return { collapsed, toggle };
}
