"use client";

import { useState, FormEvent } from "react";
import Image from "next/image";
import { Loader2, AlertTriangle } from "lucide-react";
import { createClient } from "@/lib/supabase/client";

export default function LoginPage() {
  const [email, setEmail]       = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState("");

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      // Supabase Auth owns login: it verifies the password and writes the
      // session cookies the proxy + BFF read. FastAPI only verifies the token.
      const supabase = createClient();
      const { error: signInError } = await supabase.auth.signInWithPassword({
        email,
        password,
      });

      if (signInError) {
        setError(signInError.message);
        return;
      }

      // Full navigation (not router.replace) so the proxy sees the new cookies.
      // ?next= is read from the URL directly — using useSearchParams here would
      // force this page behind a Suspense boundary.
      const next = new URLSearchParams(window.location.search).get("next");
      window.location.href = next ?? "/";
    } catch {
      setError("Could not reach Supabase. Check your network and configuration.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-8">
        {/* Brand */}
        <div className="text-center">
          <div className="inline-flex items-center justify-center mb-6">
            <Image src="/logo.png" alt="Logo" width={72} height={72} className="rounded-2xl" />
          </div>
          <p className="text-sm text-[#C4977A]">Sign in to your dashboard</p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-[#C4977A] mb-1.5">
              Email address
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
              required
              autoFocus
              className="w-full bg-[#141414] text-[#F2DEC8] text-sm rounded-xl px-4 py-3 border border-[#1e1e1e] focus:border-[#C08457] focus:outline-none placeholder-[#7a6055] transition-colors"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-[#C4977A] mb-1.5">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
              className="w-full bg-[#141414] text-[#F2DEC8] text-sm rounded-xl px-4 py-3 border border-[#1e1e1e] focus:border-[#C08457] focus:outline-none placeholder-[#7a6055] transition-colors"
            />
          </div>

          {error && (
            <div className="flex items-start gap-2.5 bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3">
              <AlertTriangle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
              <p className="text-xs text-red-400">{error}</p>
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full flex items-center justify-center gap-2 bg-[#C08457] hover:bg-[#d4a070] text-[#080808] text-sm font-semibold py-3 rounded-xl transition-colors disabled:opacity-60 mt-2"
          >
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Signing in…
              </>
            ) : (
              "Sign in"
            )}
          </button>
        </form>

      </div>
    </div>
  );
}
