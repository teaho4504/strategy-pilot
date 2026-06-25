export const won = (n: number, opts: { sign?: boolean } = {}) => {
  const sign = opts.sign && n > 0 ? "+" : "";
  return `${sign}${n.toLocaleString("ko-KR")}원`;
};
export const wonCompact = (n: number) => {
  const abs = Math.abs(n);
  if (abs >= 1e8) return `${(n / 1e8).toFixed(2)}억`;
  if (abs >= 1e4) return `${(n / 1e4).toFixed(1)}만`;
  return n.toLocaleString("ko-KR");
};
export const pct = (n: number, digits = 2) => `${n > 0 ? "+" : ""}${n.toFixed(digits)}%`;
export const timeKR = (iso: string) => {
  const d = new Date(iso);
  return d.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });
};
export const relTime = (iso: string | null) => {
  if (!iso) return "—";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "방금 전";
  if (diff < 3600) return `${Math.floor(diff / 60)}분 전`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}시간 전`;
  return `${Math.floor(diff / 86400)}일 전`;
};
