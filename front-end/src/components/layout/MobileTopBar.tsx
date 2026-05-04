import { Link } from "@tanstack/react-router";
import logo from "@/assets/sharechat-logo.png";

export function MobileTopBar() {
  return (
    <div className="lg:hidden sticky top-0 z-30 bg-background/95 backdrop-blur border-b border-border">
      <div className="flex items-center justify-between px-4 h-14">
        <Link to="/" className="flex items-center gap-2">
          <img src={logo} alt="ShareChat" className="h-9 w-9 object-contain" />
          <span className="font-bold text-lg text-muted-foreground">ShareChat</span>
        </Link>
      </div>
    </div>
  );
}
