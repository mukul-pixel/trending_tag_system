import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { LeftSidebar } from "@/components/layout/LeftSidebar";
import { BottomNav } from "@/components/layout/BottomNav";
import { MobileTopBar } from "@/components/layout/MobileTopBar";
import { SearchBar } from "@/components/layout/SearchBar";
import { TrendingSidebar } from "@/components/trending/TrendingSidebar";
import { PeopleAlsoViewed } from "@/components/trending/PeopleAlsoViewed";
import { SubscribeCard, SiteFooterMini } from "@/components/layout/SubscribeCard";
import { MoreHorizontal } from "lucide-react";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "ShareChat — Trending" },
      { name: "description", content: "Discover what India is talking about." },
    ],
  }),
  component: HomePage,
});

const TABS = [
  "Trending",
  "T20 Cricket Carnival",
  "Summer Special",
  "Wedding Season",
  "Latest",
];

const POSTS: {
  id: string;
  author: string;
  views: string;
  time: string;
  tags: string[];
  image: string;
}[] = [
  {
    id: "p1",
    author: ".★ℝ ①𝒩g 🔥♔",
    views: "13K",
    time: "4 महीने पहले",
    tags: ["किशोर कुमार सांग्स", "सदाबहार हिंदी गाने", "पुराने गाने"],
    image: "https://images.unsplash.com/photo-1583394838336-acd977736f90?w=1000&q=80",
  },
  {
    id: "p2",
    author: "Cricket Junkie",
    views: "24K",
    time: "2 घंटे पहले",
    tags: ["WorldCupFinal", "TeamIndia"],
    image: "https://images.unsplash.com/photo-1531415074968-036ba1b575da?w=1000&q=80",
  },
  {
    id: "p3",
    author: "Foodie Desi",
    views: "9.2K",
    time: "1 दिन पहले",
    tags: ["StreetFoodIndia", "Chaat"],
    image: "https://images.unsplash.com/photo-1606491956689-2ea866880c84?w=1000&q=80",
  },
  {
    id: "p4",
    author: "Monsoon Diaries",
    views: "7.8K",
    time: "6 घंटे पहले",
    tags: ["MonsoonVibes", "ChaiLover"],
    image: "https://images.unsplash.com/photo-1534030347209-467a5b0ad3e6?w=1000&q=80",
  },
];

function HomePage() {
  const [active, setActive] = useState("Trending");

  return (
    <div className="min-h-screen bg-background pb-16 lg:pb-0">
      <div className="h-1.5 w-full bg-[var(--gradient-rainbow)]" />
      <MobileTopBar />
      <div className="mx-auto max-w-[1400px] lg:grid lg:grid-cols-[auto_1fr_320px]">
        <LeftSidebar />

        {/* Main */}
        <main className="min-w-0 px-4 lg:px-8 py-6">
          <div className="max-w-2xl mx-auto mb-5">
            <SearchBar />
          </div>

          {/* Mobile trending */}
          <div className="lg:hidden mb-6">
            <TrendingSidebar initialCount={2} />
          </div>

          {/* Tabs */}
          <div className="border-b border-border mb-6">
            <div className="flex gap-6 lg:gap-8 overflow-x-auto lg:justify-center">
              {TABS.map((t) => (
                <button
                  key={t}
                  onClick={() => setActive(t)}
                  className={`relative whitespace-nowrap pb-3 pt-1 text-sm font-semibold transition-colors ${
                    active === t
                      ? "text-foreground"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {t}
                  {active === t && (
                    <span className="absolute left-0 right-0 -bottom-px h-0.5 bg-foreground rounded-full" />
                  )}
                </button>
              ))}
            </div>
          </div>

          {/* Posts */}
          <div className="space-y-6">
            {POSTS.map((post, idx) => (
              <div key={post.id}>
                <article className="max-w-2xl mx-auto rounded-2xl border border-border bg-card shadow-[var(--shadow-card)] overflow-hidden">
                  <header className="flex items-center justify-between p-4">
                    <div className="flex items-center gap-3">
                      <div className="h-10 w-10 rounded-full bg-[var(--gradient-brand)]" />
                      <div>
                        <p className="font-semibold text-sm">{post.author}</p>
                        <p className="text-xs text-muted-foreground">
                          {post.views} ने देखा · {post.time}
                        </p>
                      </div>
                    </div>
                    <MoreHorizontal className="h-5 w-5 text-muted-foreground" />
                  </header>
                  <div className="px-4 pb-3 flex flex-wrap gap-2">
                    {post.tags.map((t) => (
                      <span
                        key={t}
                        className="text-sm font-medium text-blue-600 hover:underline cursor-pointer"
                      >
                        #{t}
                      </span>
                    ))}
                  </div>
                  <img src={post.image} alt={post.author} className="w-full aspect-square object-cover" />
                </article>

                {/* People also viewed — mobile/tablet only, after 3rd post */}
                {idx === 2 && (
                  <div className="lg:hidden max-w-2xl mx-auto mt-6">
                    <PeopleAlsoViewed initialCount={2} />
                  </div>
                )}
              </div>
            ))}
          </div>
        </main>

        {/* Right */}
        <aside className="hidden lg:block w-[320px] shrink-0 px-4 py-6 space-y-5">
          <SubscribeCard />
          <TrendingSidebar />
          <SiteFooterMini />
        </aside>
      </div>
      <BottomNav />
    </div>
  );
}
