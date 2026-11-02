"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getTokens, setTokens, type Role, type User } from "./api";

/** Loads the current user; redirects to /login when signed out or to /{role} when the role does not match. */
export function useAuth(required?: Role): { user: User | null; logout: () => void } {
  const [user, setUser] = useState<User | null>(null);
  const router = useRouter();
  useEffect(() => {
    if (!getTokens()) { router.replace("/login"); return; }
    api<User>("/auth/me")
      .then((u) => {
        if (required && u.role !== required) router.replace(u.role === "RECRUITER" ? "/recruiter" : "/candidate");
        else setUser(u);
      })
      .catch(() => { setTokens(null); router.replace("/login"); });
  }, [required, router]);
  return { user, logout: () => { setTokens(null); router.replace("/login"); } };
}
