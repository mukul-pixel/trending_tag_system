import { Search } from "lucide-react";

export function SearchBar({
  placeholder = "टैग या लोगों को खोजें",
}: {
  placeholder?: string;
}) {
  return (
    <div className="relative">
      <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
      <input
        type="text"
        placeholder={placeholder}
        className="w-full h-11 rounded-full border border-border bg-card pl-11 pr-4 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring/40 focus:border-ring transition shadow-[var(--shadow-card)]"
      />
    </div>
  );
}
