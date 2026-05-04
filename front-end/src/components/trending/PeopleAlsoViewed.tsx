import { useEffect, useState } from "react";
import { Link } from "@tanstack/react-router";
import { Eye, ChevronRight, Flame } from "lucide-react";
import { getTrendingFeed, type TrendingTag } from "@/lib/trending-data";

export function PeopleAlsoViewed({
  excludeTag,
  initialCount = 2,
}: {
  excludeTag?: string;
  initialCount?: number;
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

  const filtered = tags.filter((t) => t.tag !== excludeTag);
  const visible = expanded ? filtered : filtered.slice(0, initialCount);

  if (filtered.length === 0) return null;

  return (
    <div className="rounded-2xl border border-border bg-card shadow-[var(--shadow-card)] overflow-hidden">
      <div className="px-5 pt-5 pb-3 flex items-center gap-2">
        <Eye className="h-4 w-4 text-foreground/70" />
        <h3 className="font-semibold text-base text-foreground">
          लोगों ने ये भी देखा
        </h3>
      </div>
      <ol className="divide-y divide-border">
        {visible.map((t) => (
          <li key={t.tag}>
            <Link
              to="/tag/$tagName"
              params={{ tagName: encodeURIComponent(t.tag) }}
              className="group flex gap-3 px-5 py-3.5 hover:bg-accent/60 transition-colors items-center"
            >
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
                <p className="text-xs text-muted-foreground line-clamp-1 mt-0.5">
                  {t.description}
                </p>
              </div>
              <ChevronRight className="h-4 w-4 text-muted-foreground/50" />
            </Link>
          </li>
        ))}
      </ol>
      {filtered.length > initialCount && (
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
