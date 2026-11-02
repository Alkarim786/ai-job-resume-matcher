"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, json, setTokens, type Tokens, type User } from "@/lib/api";

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const [form, setForm] = useState({ email: "", password: "", full_name: "", role: "CANDIDATE" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setForm({ ...form, [k]: e.target.value });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError("");
    try {
      const body = mode === "login" ? { email: form.email, password: form.password } : form;
      setTokens(await api<Tokens>(`/auth/${mode}`, json(body)));
      const me = await api<User>("/auth/me");
      router.replace(me.role === "RECRUITER" ? "/recruiter" : "/candidate");
    } catch (err: any) {
      setError(err.message ?? "failed");
    } finally { setBusy(false); }
  }

  return (
    <main style={{ maxWidth: 420 }}>
      <h1>{mode === "login" ? "Sign in" : "Create an account"}</h1>
      <form className="card" onSubmit={submit}>
        {mode === "register" && (<>
          <label htmlFor="n">Full name</label><input id="n" required value={form.full_name} onChange={set("full_name")} />
          <label htmlFor="r">I am a</label>
          <select id="r" value={form.role} onChange={set("role")}><option value="CANDIDATE">Candidate</option><option value="RECRUITER">Recruiter</option></select>
        </>)}
        <label htmlFor="e">Email</label><input id="e" type="email" required value={form.email} onChange={set("email")} />
        <label htmlFor="p">Password</label><input id="p" type="password" required minLength={8} value={form.password} onChange={set("password")} />
        {error && <p className="error" role="alert">{error}</p>}
        <p><button disabled={busy}>{mode === "login" ? "Sign in" : "Register"}</button></p>
      </form>
      <p className="muted">
        {mode === "login" ? <>No account? <Link href="/register">Register</Link>. Demo: candidate1@example.com / recruiter1@example.com, password <code>password123</code>.</> : <>Have an account? <Link href="/login">Sign in</Link></>}
      </p>
    </main>
  );
}
