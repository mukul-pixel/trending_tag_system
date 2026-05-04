import { useEffect, useState } from "react";
import { Link } from "@tanstack/react-router";
import { Flame, ChevronRight, Info } from "lucide-react";
import { getTrendingFeed, type TrendingTag } from "@/lib/trending-data";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

function categoryDot(category: string) {
  const map: Record<string, string> = {
    sports: "bg-emerald-500",
    music: "bg-fuchsia-500",
    lifestyle: "bg-rose-500",
    weather: "bg-sky-500",
    entertainment: "bg-amber-500",
    food: "bg-orange-500",
    technology: "bg-indigo-500",
    health: "bg-teal-500",
  };
  return map[category] ?? "bg-primary";
}

export function TrendingSidebar({
  heading = "Trending Tags",
  initialCount = 5,
  showInfo = true,
}: {
  heading?: string;
  initialCount?: number;
  showInfo?: boolean;
}) {
  const [tags, setTags] = useState<TrendingTag[]>([]);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    let active = true;
    getTrendingFeed().then((d) => {
      if (active) setTags(d);
    });
    return () => {
      active = false;
    };
  }, []);

  const visible = expanded ? tags : tags.slice(0, initialCount);

  return (
    <div className="rounded-2xl border border-border bg-card shadow-[var(--shadow-card)] overflow-hidden">
      <div className="px-5 pt-5 pb-3 flex items-center justify-between">
        <h3 className="font-semibold text-base text-foreground flex items-center gap-2">
          <Flame className="h-4 w-4 text-primary" />
          {heading}
          {showInfo && (
            <TooltipProvider delayDuration={100}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    aria-label="Trending tags के बारे में जानकारी"
                    className="text-muted-foreground hover:text-foreground transition"
                  >
                    <Info className="h-3.5 w-3.5" />
                  </button>
                </TooltipTrigger>
                <TooltipContent side="bottom" className="max-w-[260px] bg-foreground text-background">
                  <p className="text-[11px] leading-relaxed">
                    <b>ट्रेंडिंग टैग्स</b> वो टॉपिक हैं जिन पर अभी सबसे ज़्यादा
                    लोग पोस्ट और बात कर रहे हैं।
                    <br />
                    <b>Heat score</b> (0–100) बताता है कि ट्रेंड कितना तेज़ और
                    लोकप्रिय है — जितना ज़्यादा स्कोर, उतना ज़्यादा बज़।
                  </p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )}
        </h3>
        <span className="text-xs text-muted-foreground">Top {visible.length}</span>
      </div>
      <ol className="divide-y divide-border">
        {visible.map((t, i) => (
          <li key={t.tag}>
            <Link
              to="/tag/$tagName"
              params={{ tagName: encodeURIComponent(t.tag) }}
              className="group flex gap-3 px-5 py-3.5 hover:bg-accent/60 transition-colors"
            >
              <div className="flex flex-col items-center w-7 pt-0.5">
                <span className="text-lg font-bold text-muted-foreground/70 leading-none">
                  {i + 1}
                </span>
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-semibold text-sm text-foreground truncate group-hover:text-primary">
                    {t.tag}
                  </span>
                  <span className="inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-primary">
                    <Flame className="h-3 w-3" />
                    {t.heat_score}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground line-clamp-2 mt-0.5">
                  {t.description}
                </p>
                <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${categoryDot(t.category)}`}
                  />
                  <span className="text-[10px] text-muted-foreground capitalize">
                    {t.category}
                  </span>
                  {t.signals[0] && (
                    <span className="text-[10px] text-muted-foreground">
                      • {t.signals[0]}
                    </span>
                  )}
                </div>
              </div>
              <ChevronRight className="h-4 w-4 text-muted-foreground/40 self-center opacity-0 group-hover:opacity-100 transition-opacity" />
            </Link>
          </li>
        ))}
      </ol>
      {tags.length > initialCount && (
        <button
          onClick={() => setExpanded((e) => !e)}
          className="w-full text-center py-3 text-sm font-semibold text-foreground/80 hover:text-foreground hover:bg-accent/60 border-t border-border transition-colors"
        >
          {expanded ? "Show less" : "View More"}
        </button>
      )}
    </div>
  );
}
