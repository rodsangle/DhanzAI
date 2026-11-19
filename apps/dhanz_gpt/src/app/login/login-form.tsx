"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { supabaseBrowser } from "@/lib/supabase/browser";
import { safeNext } from "@/lib/safe-next";
import { Button } from "@/components/ui/button";
import { Banner } from "@/components/ui/feedback";
import { TextInput } from "@/components/ui/field";
import { TooltipProvider } from "@/components/ui/tooltip";
import { BRAND } from "@/lib/brand";

const DOMAIN = process.env.NEXT_PUBLIC_WORKSPACE_DOMAIN ?? "dhanzai.com";

const ERRORS: Record<string, string> = {
  domain: `Only @${DOMAIN} Google accounts can sign in. Switch accounts and try again.`,
  failed: "Sign-in didn't finish. Try again.",
};

function nextPath() {
  return safeNext(new URLSearchParams(window.location.search).get("next"));
}

async function post<T>(url: string, data: unknown): Promise<T> {
  const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((json as { error?: string }).error ?? "Sign-in didn't finish. Try again.");
  return json as T;
}

type Challenge = { mfa_token: string; method: "totp" | "email"; email_hint: string | null };

// S02 Sign in. DHANZ AI accounts (email, password, two-step) on the DHANZ server; Google (Supabase) for a
// workspace domain; a demo sign-in only in local dev mode.
export function LoginForm({ mode: MODE }: { mode: "supabase" | "dev" | "dhanz" }) {
  const [email, setEmail] = useState(MODE === "dev" ? "dante@rodrech.com" : "");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [challenge, setChallenge] = useState<Challenge | null>(null);
  const params = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const shownError = error ?? ERRORS[params.get("error") ?? ""] ?? null;
  const [busy, setBusy] = useState<"google" | "dev" | "dhanz" | null>(null);

  async function dhanzSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy("dhanz");
    setError(null);
    try {
      type Out = { ok?: boolean; mfa_required?: boolean } & Partial<Challenge>;
      const out = challenge
        ? await post<Out>("/api/auth/dhanz/verify", { mfa_token: challenge.mfa_token, code })
        : await post<Out>("/api/auth/dhanz/login", { email, password });
      if (out.mfa_required) {
        setChallenge({ mfa_token: out.mfa_token!, method: out.method ?? "totp", email_hint: out.email_hint ?? null });
        setPassword("");
        setBusy(null);
        return;
      }
      window.location.href = nextPath();
    } catch (err) {
      setError((err as Error).message);
      setBusy(null);
    }
  }

  async function google() {
    setBusy("google");
    setError(null);
    const { error } = await supabaseBrowser().auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo: `${window.location.origin}/auth/callback?next=${encodeURIComponent(nextPath())}`,
        queryParams: { hd: DOMAIN, prompt: "select_account" },
      },
    });
    if (error) {
      setError("Couldn't start Google sign-in. Try again.");
      setBusy(null);
    }
  }

  async function devSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy("dev");
    setError(null);
    try {
      await api.signIn(email);
      window.location.href = nextPath();
    } catch (err) {
      setError((err as Error).message);
      setBusy(null);
    }
  }

  return (
    <TooltipProvider>
      <main id="main" className="flex min-h-dvh items-center justify-center bg-surface px-4 text-fg">
        <div className="flex w-full max-w-sm flex-col gap-6 rounded-xl bg-surface-raised p-8 shadow-md">
          <div className="flex flex-col gap-1 text-center">
            <p className="text-sm font-semibold tracking-[0.2em]">{BRAND.company}</p>
            <h1 className="text-2xl font-semibold">Sign in to {BRAND.name}</h1>
            <p className="text-sm text-muted">
              {MODE === "dhanz" ? "Use your DHANZ AI account. Same email and password as dhanzai.com." : MODE === "supabase" ? "Use your work Google account." : "Local demo mode."}
            </p>
          </div>
          {shownError && <Banner tone="danger" title="Can't sign in">{shownError}</Banner>}
          {MODE === "dhanz" ? (
            <form onSubmit={dhanzSubmit} className="flex flex-col gap-4">
              {!challenge ? (
                <>
                  <TextInput label="Email" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />
                  <TextInput label="Password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
                  <Button type="submit" size="lg" loading={busy === "dhanz"}>Sign in</Button>
                  <p className="text-center text-xs text-muted">
                    No account yet, or forgot your password? Use <a className="text-accent-text underline underline-offset-2" href="https://dhanzai.com/app/">dhanzai.com</a>, then come back.
                  </p>
                </>
              ) : (
                <>
                  <p className="text-sm text-muted">
                    {challenge.method === "email"
                      ? `Enter the code we emailed${challenge.email_hint ? ` to ${challenge.email_hint}` : ""}.`
                      : "Enter the code from your authenticator app, or a recovery code."}
                  </p>
                  <TextInput label="Code" inputMode="text" autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value)} required autoFocus />
                  <Button type="submit" size="lg" loading={busy === "dhanz"}>Continue</Button>
                  <Button type="button" variant="ghost" onClick={() => { setChallenge(null); setCode(""); setError(null); }}>Start over</Button>
                </>
              )}
            </form>
          ) : MODE === "supabase" ? (
            <Button variant="secondary" size="lg" onClick={google} loading={busy === "google"}>Continue with Google</Button>
          ) : (
            <>
              <p className="text-center text-xs text-muted">Google sign-in is off in demo mode.</p>
              <form onSubmit={devSubmit} className="flex flex-col gap-4">
                <TextInput label="Work email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required hint="Try dante@rodrech.com or maya@rodrech.com" />
                <Button type="submit" size="lg" loading={busy === "dev"}>Sign in</Button>
              </form>
            </>
          )}
        </div>
      </main>
    </TooltipProvider>
  );
}
