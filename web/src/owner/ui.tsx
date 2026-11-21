import { useEffect, useState, type ReactNode } from "react";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  CircleAlert,
  LoaderCircle,
  PawPrint,
  RotateCw,
} from "lucide-react";
import type { Nav, Pet, Studio } from "./data";

export function Entry({
  title,
  intro,
  back,
  children,
  action,
}: {
  title: string;
  intro?: string;
  back?: [string, () => void];
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <main className="ow-page">
      <div className="ow-wrap">
        {back && (
          <button className="ow-back" onClick={back[1]}>
            <ArrowLeft size={15} />
            {back[0]}
          </button>
        )}
        <div className="ow-heading">
          <div>
            <h1>{title}</h1>
            {intro && <p>{intro}</p>}
          </div>
          {action}
        </div>
        {children}
      </div>
    </main>
  );
}
export function Note({ error, notice }: { error?: string; notice?: string }) {
  return (
    <>
      {error && (
        <div className="ow-notice ow-error" role="alert">
          <CircleAlert size={17} />
          {error}
        </div>
      )}
      {notice && (
        <div className="ow-notice" role="status">
          <CheckCircle2 size={17} />
          {notice}
        </div>
      )}
    </>
  );
}
export function Wait({ label }: { label: string }) {
  return (
    <div className="ow-wait" role="status">
      <LoaderCircle className="ow-spin" size={24} />
      {label}
    </div>
  );
}
export function Blank({
  title,
  text,
  action,
  label,
  icon,
}: {
  title: string;
  text: string;
  action?: () => void;
  label?: string;
  icon?: ReactNode;
}) {
  return (
    <section className="ow-blank">
      <span className="ow-blank-icon">
        {icon ?? <PawPrint size={32} strokeWidth={1.3} />}
      </span>
      <h2>{title}</h2>
      <p>{text}</p>
      {action && (
        <button className="ow-btn" onClick={action}>
          {label}
          <ArrowRight size={16} />
        </button>
      )}
    </section>
  );
}
export function SummaryImage({ pet }: { pet: Pet }) {
  return pet.photos[0] ? (
    <img src={pet.photos[0].url} alt={pet.name} loading="lazy" />
  ) : (
    <span className="ow-pet-placeholder">
      <PawPrint size={38} strokeWidth={1.35} />
    </span>
  );
}
export function DemoNote({
  data,
  kind,
}: {
  data: Studio;
  kind: "images" | "models" | "payments";
}) {
  const mode = String(data.mode?.[kind] ?? "").toLowerCase();
  if (!["demo", "local", "mock", "sandbox", "simulated"].includes(mode))
    return null;
  const content =
    kind === "payments"
      ? "演示支付不会扣款。"
      : kind === "models"
        ? "演示模式会生成示例模型，用于体验确认与交付。"
        : "演示模式会用原照制作本地效果预览。";
  return <p className="ow-demo">{content}</p>;
}
export function RefreshButton({
  refresh,
}: {
  refresh: () => Promise<unknown>;
}) {
  const [busy, setBusy] = useState(false);
  return (
    <button
      className="ow-btn ow-secondary"
      disabled={busy}
      onClick={async () => {
        setBusy(true);
        try {
          await refresh();
        } finally {
          setBusy(false);
        }
      }}
    >
      <RotateCw size={15} className={busy ? "ow-spin" : ""} />
      刷新进度
    </button>
  );
}
export function NotFound({ nav }: { nav: Nav }) {
  return (
    <Entry title="找不到这份记录">
      <Blank
        title="记录可能已归档"
        text="回到自己的宠物档案，可以继续查看和制作作品。"
        label="看我的宠物"
        action={() => nav("/pets")}
      />
    </Entry>
  );
}
export function Confirm({
  label,
  prompt,
  disabled,
  onYes,
}: {
  label: string;
  prompt: string;
  disabled?: boolean;
  onYes: () => void;
}) {
  const [ask, setAsk] = useState(false);
  useEffect(() => {
    if (disabled) setAsk(false);
  }, [disabled]);
  return ask ? (
    <div className="ow-confirm">
      <span>{prompt}</span>
      <button
        type="button"
        className="ow-btn ow-small ow-danger"
        disabled={disabled}
        onClick={() => {
          setAsk(false);
          onYes();
        }}
      >
        确认
      </button>
      <button
        type="button"
        className="ow-btn ow-small ow-plain"
        onClick={() => setAsk(false)}
      >
        取消
      </button>
    </div>
  ) : (
    <button
      type="button"
      className="ow-link ow-danger-text"
      disabled={disabled}
      onClick={() => setAsk(true)}
    >
      {label}
    </button>
  );
}
