import type { User } from "@/types/chat";
import { Icon } from "./Icon";

export function Header({ user, onLogout, loggingOut = false }: { user: User | null; onLogout?: () => void; loggingOut?: boolean }) {
  return <header className="site-header">
    <a href="/" className="brand" aria-label="Backchannel home"><span className="brand-symbol"><Icon name="chat" size={23} /></span>backchannel<span className="brand-period">.</span></a>
    <div className="header-right">
      <span className="quiet-label header-tagline">GOOD COMPANY. INTERESTING TAKES.</span>
      {user && <><span className="account-label" title={user.email}>{user.email}</span><button className="icon-button" onClick={onLogout} disabled={loggingOut} aria-label="Sign out" title="Sign out"><Icon name="logout" size={18} /></button></>}
    </div>
  </header>;
}
