"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { api, getTokens, type User } from "@/lib/api";

export default function Home() {
  const router = useRouter();
  useEffect(() => {
    if (!getTokens()) { router.replace("/login"); return; }
    api<User>("/auth/me").then((u) => router.replace(u.role === "RECRUITER" ? "/recruiter" : "/candidate")).catch(() => router.replace("/login"));
  }, [router]);
  return <main><p className="muted">Loading…</p></main>;
}
