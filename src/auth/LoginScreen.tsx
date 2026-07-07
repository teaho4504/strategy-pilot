import { FormEvent, useState } from "react";
import { LockKeyhole } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "./AuthProvider";

export function LoginScreen() {
  const { configured, signIn } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await signIn(email, password);
    } catch (err) {
      setError("로그인에 실패했습니다. 이메일과 비밀번호를 확인하세요.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-4 py-8">
      <section className="w-full max-w-[420px] rounded-2xl border border-border bg-card p-5 shadow-card">
        <div className="mb-5 flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-full bg-primary/15 text-primary">
            <LockKeyhole className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-lg font-semibold tracking-tight">Strategy Pilot</h1>
            <p className="text-xs text-muted-foreground">Supabase 인증 후 read-only 대시보드에 접속합니다.</p>
          </div>
        </div>

        {!configured ? (
          <div className="rounded-xl border border-warning/40 bg-warning-soft/40 p-3 text-sm text-warning">
            Supabase frontend 환경변수가 설정되지 않았습니다.
          </div>
        ) : (
          <form className="space-y-3" onSubmit={handleSubmit}>
            <label className="block space-y-1.5 text-sm">
              <span className="text-muted-foreground">이메일</span>
              <Input value={email} onChange={(event) => setEmail(event.target.value)} type="email" autoComplete="email" required />
            </label>
            <label className="block space-y-1.5 text-sm">
              <span className="text-muted-foreground">비밀번호</span>
              <Input value={password} onChange={(event) => setPassword(event.target.value)} type="password" autoComplete="current-password" required />
            </label>
            {error && <div className="rounded-lg border border-danger/40 bg-danger-soft/40 px-3 py-2 text-xs text-danger">{error}</div>}
            <Button type="submit" className="w-full" disabled={submitting}>
              {submitting ? "로그인 중" : "로그인"}
            </Button>
          </form>
        )}

        <p className="mt-4 text-center text-[11px] text-muted-foreground">
          주문 기능은 비활성화되어 있으며, 서버는 mock/read-only 상태를 유지합니다.
        </p>
      </section>
    </main>
  );
}
