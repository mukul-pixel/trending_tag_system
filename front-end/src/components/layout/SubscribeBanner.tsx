import { useState } from "react";
import { X, Sparkles } from "lucide-react";

export function SubscribeBanner() {
  const [hidden, setHidden] = useState(false);
  if (hidden) return null;
  return (
    <div className="flex items-center gap-3 rounded-2xl border border-border bg-card px-4 py-3 shadow-[var(--shadow-card)]">
      <Sparkles className="h-4 w-4 text-primary shrink-0" />
      <p className="text-sm font-medium text-foreground flex-1">
        Subscribe to <span className="text-primary font-semibold">SC PLUS</span>
      </p>
      <button
        onClick={() => setHidden(true)}
        aria-label="Dismiss"
        className="h-7 w-7 rounded-full hover:bg-accent flex items-center justify-center text-muted-foreground hover:text-foreground transition"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}
