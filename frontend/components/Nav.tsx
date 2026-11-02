"use client";
import type { User } from "@/lib/api";

export function Nav({ user, onLogout }: { user: User; onLogout: () => void }) {
  return (
    <div className="nav">
      <strong>Job &amp; Resume Matcher</strong>
      <span>
        <span className="muted">{user.full_name} · {user.role.toLowerCase()}</span>{" "}
        <button className="ghost" onClick={onLogout}>Sign out</button>
      </span>
    </div>
  );
}
