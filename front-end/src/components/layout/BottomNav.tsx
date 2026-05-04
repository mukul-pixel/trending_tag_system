import { Home, Compass, Wallet, Clapperboard, UserCircle2 } from "lucide-react";
import { Link } from "@tanstack/react-router";

const ITEMS = [
  { icon: Home, label: "Home", to: "/" },
  { icon: Compass, label: "Explore", to: "/" },
  { icon: Clapperboard, label: "Video", to: "/" },
  { icon: Wallet, label: "Wallet", to: "/" },
  { icon: UserCircle2, label: "Profile", to: "/" },
];

export function BottomNav() {
  return (
    <nav className="lg:hidden fixed bottom-0 inset-x-0 z-40 bg-background/95 backdrop-blur border-t border-border">
      <ul className="grid grid-cols-5">
        {ITEMS.map((it) => (
          <li key={it.label}>
            <Link
              to={it.to}
              className="flex flex-col items-center gap-0.5 py-2.5 text-foreground/75 hover:text-primary transition-colors"
            >
              <it.icon className="h-5 w-5" />
              <span className="text-[10px] font-medium">{it.label}</span>
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
