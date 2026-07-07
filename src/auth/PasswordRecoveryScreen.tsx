import { FormEvent, useState } from "react";
import { KeyRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "./AuthProvider";

export function PasswordRecoveryScreen() {
  const { updateRecoveryPassword } = useAuth();
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);

    if (password.length < 8) {
      setError("비밀번호는 8자 이상으로 설정하세요.");
      return;
    }

    if (password !== confirmPassword) {
      setError("새 비밀번호가 서로 일치하지 않습니다.");
      return;
    }

    setSubmitting(true);
    try {
      await updateRecoveryPassword(password);
    } catch (err) {
      setError("비밀번호 설정에 실패했습니다. 재설정 링크를 다시 요청하세요.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-4 py-8">
      <section className="w-full max-w-[420px] rounded-2xl border border-border bg-card p-5 shadow-card">
        <div className="mb-5 flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-full bg-primary/15 text-primary">
            <KeyRound className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-lg font-semibold tracking-tight">새 비밀번호 설정</h1>
            <p className="text-xs text-muted-foreground">설정이 끝나면 다시 로그인해야 합니다.</p>
          </div>
        </div>

        <form className="space-y-3" onSubmit={handleSubmit}>
          <label className="block space-y-1.5 text-sm">
            <span className="text-muted-foreground">새 비밀번호</span>
            <Input value={password} onChange={(event) => setPassword(event.target.value)} type="password" autoComplete="new-password" required />
          </label>
          <label className="block space-y-1.5 text-sm">
            <span className="text-muted-foreground">새 비밀번호 확인</span>
            <Input value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} type="password" autoComplete="new-password" required />
          </label>
          {error && <div className="rounded-lg border border-danger/40 bg-danger-soft/40 px-3 py-2 text-xs text-danger">{error}</div>}
          <Button type="submit" className="w-full" disabled={submitting}>
            {submitting ? "설정 중" : "비밀번호 설정"}
          </Button>
        </form>
      </section>
    </main>
  );
}
