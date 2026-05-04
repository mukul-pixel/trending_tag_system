import { Link } from "@tanstack/react-router";
import logo from "@/assets/sharechat-logo.png";
import {
  Home,
  Compass,
  Wallet,
  Clapperboard,
  UserCircle2,
  TrendingUp,
  Languages,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useSidebarCollapsed } from "@/hooks/use-sidebar";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

const ITEMS: { icon: LucideIcon; label: string; to: string }[] = [
  { icon: Home, label: "Home", to: "/" },
  { icon: Compass, label: "Explore", to: "/" },
  { icon: Wallet, label: "Wallet", to: "/" },
  { icon: Clapperboard, label: "Video", to: "/" },
  { icon: UserCircle2, label: "Profile", to: "/" },
  { icon: TrendingUp, label: "Trends", to: "/" },
  { icon: Languages, label: "Hindi", to: "/" },
];

export function LeftSidebar() {
  const { collapsed, toggle } = useSidebarCollapsed();

  return (
    <aside
      className={`hidden lg:flex flex-col py-6 sticky top-0 h-screen shrink-0 border-r border-border bg-background transition-all ${
        collapsed ? "w-[72px] px-2" : "w-[250px] px-4"
      }`}
    >
      <div
        className={`mb-6 flex items-center ${
          collapsed ? "flex-col gap-3" : "justify-between"
        }`}
      >
        <Link to="/" className="flex items-center gap-2 px-1">
          <img src={logo} alt="ShareChat" className="h-9 w-9 object-contain" />
          {!collapsed && (
            <span className="font-bold text-lg text-muted-foreground">
              ShareChat
            </span>
          )}
        </Link>
        <button
          onClick={toggle}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className="h-8 w-8 rounded-lg hover:bg-accent flex items-center justify-center text-muted-foreground hover:text-foreground transition"
        >
          {collapsed ? (
            <PanelLeftOpen className="h-4 w-4" />
          ) : (
            <PanelLeftClose className="h-4 w-4" />
          )}
        </button>
      </div>

      <TooltipProvider delayDuration={100}>
        <nav className="flex flex-col gap-1">
          {ITEMS.map((it) => {
            const link = (
              <Link
                key={it.label}
                to={it.to}
                className={`flex items-center gap-3 rounded-xl hover:bg-accent transition-colors text-foreground/85 hover:text-foreground ${
                  collapsed ? "justify-center p-2.5" : "px-3 py-2.5"
                }`}
              >
                <it.icon className="h-5 w-5" />
                {!collapsed && (
                  <span className="text-sm font-medium">{it.label}</span>
                )}
              </Link>
            );
            if (!collapsed) return link;
            return (
              <Tooltip key={it.label}>
                <TooltipTrigger asChild>{link}</TooltipTrigger>
                <TooltipContent side="right">{it.label}</TooltipContent>
              </Tooltip>
            );
          })}
        </nav>
      </TooltipProvider>
    </aside>
  );
}
