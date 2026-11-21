import { useEffect, useRef, useState } from "react";
import { X, Inbox } from "lucide-react";
export type Row = Record<string, any>;
export type Run = (
  path: string,
  body?: unknown,
  method?: string,
) => Promise<boolean>;
export const label: Record<string, string> = {
  unpaid: "待支付",
  paid: "已付款",
  refunded: "已退款",
  refunding: "退款中",
  cancelled: "已取消",
  canceled: "已取消",
  queued: "排队中",
  pending: "待处理",
  running: "处理中",
  processing: "生成中",
  ready: "已生成",
  succeeded: "已完成",
  done: "已完成",
  failed: "失败",
  uncertain: "待核对",
  delivered: "已交付",
  locked: "待解锁",
  waiting: "等待中",
  none: "无需生成",
  requested: "待报价",
  quoted: "已报价",
  accepted: "主人已接受",
  declined: "主人已婉拒",
  owner: "宠物主人",
  admin: "管理员",
  operator: "运营",
  created: "已创建",
  awaiting_payment: "待付款",
  awaiting_review: "等待验收",
  awaiting_confirmation: "等待确认",
  awaiting_material: "待补资料",
  needs_photos: "待补资料",
  needs_info: "待补资料",
  review: "待验收",
  blocked: "待处理",
  stopped: "已停止",
  not_started: "未开始",
  in_progress: "进行中",
  model: "3D 模型",
  portrait: "纪念肖像",
};
export const fmt = (s: string) =>
  s
    ? new Date(s).toLocaleString("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";
export const abbr = (s: string) =>
  s?.length > 16 ? s.slice(0, 5) + "…" + s.slice(-6) : s;
export function Tag({ value }: { value: string }) {
  return (
    <span className={"adm-tag tag-" + value}>
      {label[value] || value || "—"}
    </span>
  );
}
export function Blank({ children }: { children: React.ReactNode }) {
  return (
    <div className="adm-blank">
      <Inbox size={24} />
      <p>{children}</p>
    </div>
  );
}
export function Field({
  children,
  title,
}: {
  children: React.ReactNode;
  title: string;
}) {
  return (
    <label className="adm-field">
      <span>{title}</span>
      {children}
    </label>
  );
}
export type Action = {
  title: string;
  detail?: string;
  field?: string;
  optional?: boolean;
  amount?: boolean;
  reason?: boolean;
  options?: { id: string; name: string }[];
  danger?: boolean;
  submit: (note: string, amount: string, option: string) => Promise<boolean>;
};
export function ActionDialog({
  action,
  onClose,
}: {
  action: Action;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const [note, setNote] = useState(""),
    [amount, setAmount] = useState(""),
    [option, setOption] = useState(action.options?.[0]?.id || ""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    ref.current?.showModal();
    const r = ref.current;
    return () => r?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      className="adm-dialog"
      onCancel={(e) => {
        if (busy) e.preventDefault();
        else onClose();
      }}
    >
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            if (await action.submit(note, amount, option)) onClose();
            else
              setError(
                "未能完成处理，请核对资料。关闭后可查看后台的详细说明。",
              );
          } finally {
            setBusy(false);
          }
        }}
      >
        <button
          type="button"
          disabled={busy}
          className="adm-close"
          aria-label="关闭"
          onClick={onClose}
        >
          <X size={18} />
        </button>
        <h3>{action.title}</h3>
        {action.detail && <p>{action.detail}</p>}
        {action.amount && (
          <Field title="报价（人民币元）">
            <input
              required
              type="number"
              min=".01"
              max="100000"
              step=".01"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
          </Field>
        )}
        {action.options && (
          <Field title="处理方式">
            <select value={option} onChange={(e) => setOption(e.target.value)}>
              {action.options.map((o) => (
                <option value={o.id} key={o.id}>
                  {o.name}
                </option>
              ))}
            </select>
          </Field>
        )}
        {action.field && (
          <Field title={action.field}>
            <textarea
              autoFocus
              required={!action.optional}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              maxLength={1400}
              rows={3}
            />
          </Field>
        )}
        {error && (
          <p role="alert" className="adm-error">
            {error}
          </p>
        )}
        <div className="adm-actions">
          <button type="button" onClick={onClose} disabled={busy}>
            返回
          </button>
          <button
            className={action.danger ? "adm-danger" : "adm-primary"}
            disabled={busy}
          >
            {busy ? "正在处理…" : "确认" + action.title}
          </button>
        </div>
      </form>
    </dialog>
  );
}
