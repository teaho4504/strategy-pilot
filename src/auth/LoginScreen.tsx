import { FormEvent, useState } from "react";
import { KeyRound, RefreshCw, ShieldCheck, TerminalSquare } from "lucide-react";
import { ApiClientError, KiwoomCliProfileSummary, getKiwoomCliProfiles } from "@/services/apiClient";
import { useAuth } from "./AuthProvider";

function kiwoomLoginErrorMessage(error: ApiClientError): string {
  if (error.returnCode === "TOKEN_ENDPOINT_REDIRECT") {
    return "키움 토큰 서버가 정상 응답 대신 다른 페이지로 연결해 로그인을 안전하게 차단했습니다. 잠시 후 로그인 버튼으로 다시 시도하세요.";
  }
  if (error.returnCode === "TIMEOUT") {
    return "키움 토큰 서버 응답 시간이 초과되었습니다. 네트워크 상태를 확인한 뒤 다시 시도하세요.";
  }
  if (error.returnCode === "NETWORK_ERROR") {
    return "키움 토큰 서버에 연결하지 못했습니다. 네트워크 상태를 확인한 뒤 다시 시도하세요.";
  }
  if (error.returnCode || error.returnMessage) {
    return `키움 오류 ${error.returnCode ?? "-"} · ${error.returnMessage ?? "CLI 프로필 접근토큰 발급 실패"}`;
  }
  return "저장된 키움 CLI 프로필로 로그인하지 못했습니다. kiwoomcli 설정 상태를 확인하세요.";
}

export function LoginScreen() {
  const { signInWithProfile } = useAuth();
  const [profiles, setProfiles] = useState<KiwoomCliProfileSummary[]>([]);
  const [profilesLoaded, setProfilesLoaded] = useState(true);
  const [profileLoadError, setProfileLoadError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [profileSubmitting, setProfileSubmitting] = useState<string | null>(null);
  const [accessPin, setAccessPin] = useState("");

  const loadProfiles = (event?: FormEvent) => {
    event?.preventDefault();
    const pin = accessPin.trim();
    if (!pin) {
      setProfileLoadError("대시보드 접근 PIN을 입력하세요.");
      setProfilesLoaded(true);
      return;
    }
    setProfilesLoaded(false);
    setProfileLoadError(null);
    getKiwoomCliProfiles(pin)
      .then((items) => {
        setProfiles(items);
      })
      .catch((err) => {
        setProfiles([]);
        setProfileLoadError(err instanceof ApiClientError ? `${err.status ?? "-"} · ${err.message}` : "profile_load_failed");
      })
      .finally(() => {
        setProfilesLoaded(true);
      });
  };

  const handleProfileLogin = async (profile?: string) => {
    const pin = accessPin.trim();
    if (!pin) {
      setError("대시보드 접근 PIN을 입력하세요.");
      return;
    }
    setError(null);
    setProfileSubmitting(profile || "current");
    try {
      await signInWithProfile(profile, pin);
    } catch (err) {
      setError(err instanceof ApiClientError
        ? kiwoomLoginErrorMessage(err)
        : "저장된 키움 CLI 프로필로 로그인하지 못했습니다. kiwoomcli 설정 상태를 확인하세요.");
    } finally {
      setProfileSubmitting(null);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-4 py-8">
      <section className="w-full max-w-[430px] rounded-2xl border border-border bg-card p-5 shadow-card">
        <div className="mb-5 flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-full bg-primary/15 text-primary">
            <KeyRound className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-lg font-semibold tracking-tight">키움 계좌 로그인</h1>
            <p className="text-xs text-muted-foreground">대시보드 PIN 확인 후 저장된 CLI 프로필로 서버 세션을 생성합니다.</p>
          </div>
        </div>

        <div className="mb-4 rounded-xl border border-primary/25 bg-primary/10 p-3 text-[11px] leading-5 text-primary">
          <div className="font-semibold text-primary">App Key / Secret Key 입력 없음</div>
          <p className="mt-1">
            키움 CLI에 저장된 운영체제 자격 증명 값을 사용합니다. Windows에서는 자격 증명 관리자에 저장됩니다. 계좌별 키 변경이나 추가는 PowerShell에서
            <span className="num mx-1 rounded bg-background/70 px-1 py-0.5">kiwoomcli auth login --alias &quot;계좌별칭&quot; --mode real</span>
            으로 처리합니다. 여러 계좌는 계좌마다 서로 다른 별칭으로 한 번씩 등록하세요.
          </p>
        </div>

        <form className="mb-4 space-y-2" onSubmit={loadProfiles}>
          <label className="block text-xs font-medium text-muted-foreground" htmlFor="dashboard-access-pin">
            대시보드 접근 PIN
          </label>
          <div className="flex gap-2">
            <input
              id="dashboard-access-pin"
              type="password"
              value={accessPin}
              onChange={(event) => setAccessPin(event.target.value)}
              autoComplete="current-password"
              className="min-w-0 flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none transition focus:border-primary"
              placeholder="서버 시작 시 표시된 PIN"
            />
            <button
              type="submit"
              disabled={!accessPin.trim() || profileSubmitting !== null || !profilesLoaded}
              className="rounded-lg bg-primary px-3 py-2 text-xs font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
            >
              프로필 조회
            </button>
          </div>
        </form>

        <div className="mb-4 rounded-xl border border-primary/25 bg-primary/5 p-3">
          <div className="mb-2 flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <TerminalSquare className="h-4 w-4 text-primary" />
              <span className="text-sm font-semibold text-foreground">저장된 키움 CLI 프로필</span>
              {profilesLoaded && !profileLoadError && profiles.length > 0 && (
                <span className="rounded-full border border-primary/30 bg-primary/10 px-2 py-0.5 text-[10px] font-semibold text-primary">
                  {profiles.length}개 등록
                </span>
              )}
            </div>
            <button
              type="button"
              onClick={() => loadProfiles()}
              disabled={!profilesLoaded || profileSubmitting !== null}
              className="grid h-8 w-8 place-items-center rounded-lg border border-border bg-surface-3 text-muted-foreground transition hover:border-primary/50 hover:text-primary disabled:opacity-50"
              aria-label="프로필 새로고침"
            >
              <RefreshCw className="h-3.5 w-3.5" />
            </button>
          </div>
          {!profilesLoaded && <p className="text-xs text-muted-foreground">프로필을 확인하는 중입니다.</p>}
          {profilesLoaded && !profileLoadError && profiles.length === 0 && !accessPin.trim() && (
            <p className="text-xs leading-5 text-muted-foreground">
              먼저 대시보드 접근 PIN을 입력한 뒤 프로필을 조회하세요.
            </p>
          )}
          {profilesLoaded && profileLoadError && (
            <div className="rounded-lg border border-danger/40 bg-danger-soft/40 px-3 py-2 text-xs leading-5 text-danger">
              키움 CLI 프로필 조회 실패: {profileLoadError}
              <br />
              백엔드 주소와 Vite 환경변수 VITE_API_BASE_URL을 확인하세요.
            </div>
          )}
          {profilesLoaded && !profileLoadError && profiles.length === 0 && accessPin.trim() && (
            <p className="text-xs leading-5 text-muted-foreground">
              저장된 프로필이 없습니다. PowerShell에서 계좌별 별칭으로 키움 CLI 인증을 완료하면 App Key와 Secret Key를
              브라우저에 다시 입력하지 않고 로그인할 수 있습니다.
            </p>
          )}
          {profiles.length > 0 && (
            <div className="space-y-2">
              {profiles.map((profile) => (
                <button
                  key={profile.profile}
                  type="button"
                  onClick={() => handleProfileLogin(profile.profile)}
                  disabled={profileSubmitting !== null}
                  className="flex w-full items-center justify-between rounded-lg border border-border bg-surface-3 px-3 py-2 text-left transition hover:border-primary/50 disabled:opacity-60"
                >
                  <span>
                    <span className="block text-sm font-semibold text-foreground">
                      {profile.profile}
                      {profile.current ? " · 현재" : ""}
                    </span>
                    <span className="text-[11px] text-muted-foreground">
                      실전투자 · {profile.accountLabel} · Windows 자격 증명 관리자 저장값 사용
                    </span>
                  </span>
                  <span className="text-xs font-semibold text-primary">
                    {profileSubmitting === profile.profile ? "접속 중" : "로그인"}
                  </span>
                </button>
              ))}
              <p className="px-1 pt-1 text-[11px] leading-5 text-muted-foreground">
                등록한 계좌 수만큼 로그인 버튼이 표시됩니다. 계좌별 App Key와 App Secret은 브라우저가 아닌 Windows 자격 증명
                관리자에서 분리 보관됩니다.
              </p>
            </div>
          )}
        </div>

        {error && <div className="rounded-lg border border-danger/40 bg-danger-soft/40 px-3 py-2 text-xs text-danger">{error}</div>}

        <div className="mt-4 flex items-start gap-2 rounded-xl border border-primary/25 bg-primary/10 p-3 text-[11px] leading-5 text-primary">
          <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
          <p>
            App Key와 Secret Key는 브라우저에 입력하거나 저장하지 않습니다. 백엔드는 키움 접근토큰 발급 후 임시 세션만
            대시보드에 전달합니다.
          </p>
        </div>
      </section>
    </main>
  );
}
