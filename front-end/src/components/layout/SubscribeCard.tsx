export function SubscribeCard() {
  return (
    <div className="rounded-2xl border border-border bg-card p-5 shadow-[var(--shadow-card)]">
      <h3 className="font-semibold text-base">Subscribe to SC PLUS</h3>
      <p className="text-sm text-muted-foreground mt-1.5 leading-relaxed">
        Subscribe to get access to exclusive content, ad-free experience, and
        more.
      </p>
      <button className="mt-4 px-5 py-2 rounded-full bg-foreground text-background text-sm font-semibold hover:opacity-90 transition">
        Subscribe
      </button>
    </div>
  );
}

export function SiteFooterMini() {
  return (
    <div className="px-2 pt-2 text-xs text-muted-foreground">
      <div className="flex flex-wrap gap-x-4 gap-y-1 font-medium text-foreground/80">
        <a href="#">About Us</a>
        <a href="#">Team</a>
        <a href="#">Careers</a>
        <a href="#">Blogs</a>
        <a href="#">News</a>
        <a href="#">Get in Touch</a>
      </div>
      <p className="mt-2">Copyright © 2026 Mohalla Tech Private Limited.</p>
    </div>
  );
}
