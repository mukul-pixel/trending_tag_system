import { createFileRoute, Link, useRouter } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { ArrowLeft, Share2, Flame, MoreHorizontal, Heart, MessageCircle } from "lucide-react";
import { LeftSidebar } from "@/components/layout/LeftSidebar";
import { BottomNav } from "@/components/layout/BottomNav";
import { SearchBar } from "@/components/layout/SearchBar";
import { TrendingSidebar } from "@/components/trending/TrendingSidebar";
import { PeopleAlsoViewed } from "@/components/trending/PeopleAlsoViewed";
import { SubscribeCard, SiteFooterMini } from "@/components/layout/SubscribeCard";
import {
  getTrendDetails,
  getRankFor,
  type TrendDetails,
} from "@/lib/trending-data";

export const Route = createFileRoute("/tag/$tagName")({
  head: ({ params }) => {
    const name = decodeURIComponent(params.tagName);
    return {
      meta: [
        { title: `${name} — Trending on ShareChat` },
        {
          name: "description",
          content: `See top posts and trending discussions about ${name} on ShareChat.`,
        },
        { property: "og:title", content: `${name} — Trending on ShareChat` },
      ],
    };
  },
  component: TagDetailPage,
});

function TagDetailPage() {
  const { tagName } = Route.useParams();
  const router = useRouter();
  const [data, setData] = useState<TrendDetails | null>(null);
  const decoded = decodeURIComponent(tagName);
  const rank = getRankFor(decoded);

  useEffect(() => {
    let active = true;
    setData(null);
    getTrendDetails(tagName).then((d) => {
      if (active) setData(d);
    });
    return () => {
      active = false;
    };
  }, [tagName]);

  return (
    <div className="min-h-screen bg-background pb-16 lg:pb-0">
      <div className="h-1.5 w-full bg-[var(--gradient-rainbow)]" />
      <div className="mx-auto max-w-[1400px] lg:grid lg:grid-cols-[auto_1fr_320px]">
        <LeftSidebar />

        <main className="min-w-0 px-4 lg:px-8 py-6">
          <div className="max-w-2xl mx-auto mb-5">
            <SearchBar />
          </div>

          {/* Detail header */}
          <div className="sticky top-0 z-10 bg-background/90 backdrop-blur border-b border-border -mx-4 lg:-mx-8 px-4 lg:px-8">
            <div className="max-w-2xl mx-auto grid grid-cols-3 items-center py-3">
              <div className="flex justify-start">
                <button
                  onClick={() => router.history.back()}
                  className="h-10 w-10 rounded-full hover:bg-accent flex items-center justify-center transition"
                  aria-label="Back"
                >
                  <ArrowLeft className="h-5 w-5" />
                </button>
              </div>
              <Link to="/" className="font-bold text-lg text-muted-foreground text-center">
                ShareChat
              </Link>
              <div className="flex justify-end">
                <button
                  className="h-10 w-10 rounded-full hover:bg-accent flex items-center justify-center transition"
                  aria-label="Share"
                >
                  <Share2 className="h-5 w-5" />
                </button>
              </div>
            </div>
          </div>

          <div className="max-w-2xl mx-auto pt-6">
            {!data ? (
              <div className="space-y-4">
                <div className="h-8 w-2/3 bg-muted animate-pulse rounded" />
                <div className="aspect-video bg-muted animate-pulse rounded-2xl" />
                <div className="h-20 bg-muted animate-pulse rounded" />
              </div>
            ) : (
              <>
                <div className="flex items-center gap-2 text-xs font-semibold text-primary uppercase tracking-wider mb-2">
                  <Flame className="h-3.5 w-3.5" />
                  #Trending {rank}
                </div>
                <h1 className="text-3xl md:text-4xl font-bold tracking-tight text-foreground mb-5">
                  {data.tag_name}
                </h1>

                <div className="rounded-2xl overflow-hidden border border-border shadow-[var(--shadow-card)] mb-6">
                  <img
                    src={data.hero_url}
                    alt={data.tag_name}
                    className="w-full h-72 object-cover"
                  />
                </div>

                <p className="text-base leading-relaxed text-foreground/85 mb-10">
                  {data.about_trend}
                </p>

                <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
                  <Flame className="h-5 w-5 text-primary" />
                  Trending Posts
                </h2>

                <div className="space-y-5">
                  {data.posts.map((p, idx) => (
                    <div key={p.id}>
                    <article
                      className="rounded-2xl border border-border bg-card shadow-[var(--shadow-card)] overflow-hidden"
                    >
                      <header className="flex items-center justify-between p-4">
                        <div className="flex items-center gap-3">
                          <div className="h-10 w-10 rounded-full bg-[var(--gradient-brand)]" />
                          <div>
                            <p className="font-semibold text-sm">{p.author}</p>
                            <p className="text-xs text-muted-foreground">
                              {p.views} views · {p.time_ago}
                            </p>
                          </div>
                        </div>
                        <MoreHorizontal className="h-5 w-5 text-muted-foreground" />
                      </header>
                      <p className="px-4 pb-3 text-sm leading-relaxed">
                        {p.caption}
                      </p>
                      <div className="px-4 pb-3 flex gap-2 flex-wrap">
                        {p.tags.map((t) => (
                          <span
                            key={t}
                            className="text-xs font-semibold text-blue-600 hover:underline cursor-pointer"
                          >
                            {t.startsWith("#") ? t : `#${t}`}
                          </span>
                        ))}
                      </div>
                      <img
                        src={p.image_url}
                        alt={p.caption}
                        className="w-full aspect-video object-cover"
                      />
                      <div className="flex items-center gap-6 px-4 py-3 text-muted-foreground">
                        <button className="flex items-center gap-1.5 text-sm hover:text-primary transition">
                          <Heart className="h-4 w-4" /> Like
                        </button>
                        <button className="flex items-center gap-1.5 text-sm hover:text-primary transition">
                          <MessageCircle className="h-4 w-4" /> Comment
                        </button>
                        <button className="flex items-center gap-1.5 text-sm hover:text-primary transition ml-auto">
                          <Share2 className="h-4 w-4" /> Share
                        </button>
                      </div>
                    </article>
                    {idx === 2 && (
                      <div className="lg:hidden mt-5">
                        <PeopleAlsoViewed excludeTag={decoded} initialCount={2} />
                      </div>
                    )}
                    </div>
                  ))}
                </div>

              </>
            )}
          </div>
        </main>

        <aside className="hidden lg:block w-[320px] shrink-0 px-4 py-6 space-y-5">
          <SubscribeCard />
          <TrendingSidebar heading="More Trending Tags" />
          <SiteFooterMini />
        </aside>
      </div>
      <BottomNav />
    </div>
  );
}
