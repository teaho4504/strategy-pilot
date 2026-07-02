import { useState } from "react";
import { Power, ShieldAlert } from "lucide-react";
import { useApp } from "@/store/app";
import { Card } from "@/components/common/Card";
import { Switch } from "@/components/ui/switch";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { toast } from "sonner";
import { strategyAdapter } from "@/services/adapters";

const automationLabel = { idle: "대기", running: "실행 중", paused: "일시정지" } as const;

export function AutomationControl() {
  const { automation, setAutomation } = useApp();
  const [confirmToggle, setConfirmToggle] = useState<null | "on" | "off">(null);
  const [killStep, setKillStep] = useState<0 | 1 | 2>(0);

  const isOn = automation === "running";

  const onToggle = (checked: boolean) => setConfirmToggle(checked ? "on" : "off");
  const applyToggle = () => {
    setAutomation(confirmToggle === "on" ? "running" : "paused");
    toast.success(confirmToggle === "on" ? "자동매매를 시작합니다 (데모)" : "자동매매를 일시정지했습니다 (데모)");
    setConfirmToggle(null);
  };

  const killAll = async () => {
    setAutomation("paused");
    await strategyAdapter.pauseAll();
    toast.error("Kill Switch · 모든 전략이 즉시 중지되었습니다 (데모)");
    setKillStep(0);
  };

  return (
    <Card className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1">
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">전체 자동매매</div>
          <div className="flex items-center gap-2">
            <span className={`h-2.5 w-2.5 rounded-full ${isOn ? "bg-success animate-pulse" : "bg-warning"}`} />
            <span className="text-lg font-semibold">{automationLabel[automation]}</span>
          </div>
          <p className="text-xs text-muted-foreground">기본값은 모의투자 · 일시정지입니다.</p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <Switch checked={isOn} onCheckedChange={onToggle} aria-label="자동매매 전체 토글" />
          <span className="text-[11px] text-muted-foreground">{isOn ? "ON" : "OFF"}</span>
        </div>
      </div>

      <button
        onClick={() => setKillStep(1)}
        className="group flex w-full items-center justify-between gap-3 rounded-xl border border-danger/40 bg-danger-soft/60 px-4 py-3 text-left transition-colors hover:bg-danger-soft"
      >
        <span className="flex items-center gap-3">
          <span className="grid h-9 w-9 place-items-center rounded-lg bg-danger/20 text-danger">
            <ShieldAlert className="h-[18px] w-[18px]" />
          </span>
          <span>
            <span className="block text-sm font-semibold text-danger">Kill Switch · 전체 즉시 중지</span>
            <span className="block text-[11px] text-danger/80">모든 전략 정지 · 대기 주문 취소 (데모)</span>
          </span>
        </span>
        <Power className="h-5 w-5 text-danger/70 group-hover:text-danger" />
      </button>

      <AlertDialog open={confirmToggle !== null} onOpenChange={(o) => !o && setConfirmToggle(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              자동매매를 {confirmToggle === "on" ? "시작" : "일시정지"}하시겠어요?
            </AlertDialogTitle>
            <AlertDialogDescription>
              이 동작은 데모 환경에서만 적용됩니다. 실제 증권사 주문은 발생하지 않습니다.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>취소</AlertDialogCancel>
            <AlertDialogAction onClick={applyToggle}>
              {confirmToggle === "on" ? "시작" : "일시정지"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={killStep > 0} onOpenChange={(o) => !o && setKillStep(0)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="text-danger">
              {killStep === 1 ? "정말 모든 전략을 중지할까요?" : "다시 한 번 확인합니다"}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {killStep === 1
                ? "실행 중인 모든 전략을 즉시 중지하고 대기 주문을 취소합니다. 다음 단계에서 한 번 더 확인합니다."
                : "이 동작은 되돌릴 수 없습니다. 계속하려면 '전체 중지'를 누르세요. (데모)"}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>취소</AlertDialogCancel>
            {killStep === 1 ? (
              <AlertDialogAction
                onClick={(e) => { e.preventDefault(); setKillStep(2); }}
                className="bg-danger text-destructive-foreground hover:bg-danger/90"
              >
                다음
              </AlertDialogAction>
            ) : (
              <AlertDialogAction
                onClick={killAll}
                className="bg-danger text-destructive-foreground hover:bg-danger/90"
              >
                전체 중지
              </AlertDialogAction>
            )}
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
