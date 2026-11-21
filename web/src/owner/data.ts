import { api } from "../common";
export { api } from "../common";
import { useCallback, useEffect, useRef, useState } from "react";

export type Id = string | number;
export type Nav = (path: string) => void;
export interface Account {
  id: Id;
  name: string;
  email?: string;
  role?: string;
}
export interface Photo {
  original_url?: string;
  id: Id;
  name: string;
  url: string;
}
export interface Pet {
  id: Id;
  name: string;
  species: string;
  traits: string;
  story: string;
  occasion: string;
  photos: Photo[];
  created_at: string;
}
export interface Style {
  id: Id;
  name: string;
  active: boolean;
  prompt?: string;
}
export interface Candidate {
  id: Id;
  preview_url: string;
}
export interface Work {
  id: Id;
  pet_id: Id;
  kind: string;
  title: string;
  status: string;
  style_id: Id;
  photo_ids?: Id[];
  candidates: Candidate[];
  feedback?: string;
  revision_count: number;
  created_at: string;
  error?: string;
  message?: string;
}
export interface Order {
  id: Id;
  pet_id: Id;
  kind: string;
  amount: number;
  payment_status: string;
  generation_status: string;
  delivery_status: string;
  candidate_id?: Id;
  owner_confirmed: boolean;
  quality_checked: boolean;
  preview_url?: string;
  downloads: { name: string; url: string }[];
  created_at: string;
  revision_count?: number;
  support?: string;
  support_reply?: string;
  supplement_note?: string;
  status?: string;
  error?: string;
}
export interface Sample {
  id: Id;
  order_id: Id;
  specs: string;
  status: string;
  quote: number | string | null;
  note: string;
}
export interface Studio {
  user: Account | null;
  mode: Record<string, string>;
  styles: Style[];
  prices: { portrait: number; model: number };
  pets: Pet[];
  works: Work[];
  orders: Order[];
  samples: Sample[];
}
export const same = (a: unknown, b: unknown) =>
  a != null && b != null && String(a) === String(b);
export const money = (cents: number) =>
  "¥" +
  (cents / 100).toLocaleString("zh-CN", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  });
export const dateText = (at: string) => {
  const date = new Date(at);
  return Number.isNaN(date.getTime())
    ? ""
    : date.toLocaleDateString("zh-CN", {
        year: "numeric",
        month: "long",
        day: "numeric",
      });
};
export const petLink = (pet: Pet) => "/pets/" + encodeURIComponent(pet.id);
export const portraitLink = (pet: Pet) =>
  "/create/portrait?pet=" + encodeURIComponent(pet.id);
export const modelLink = (pet: Pet) =>
  "/create/model?pet=" + encodeURIComponent(pet.id);
export const orderLink = (o: Order) => "/orders/" + encodeURIComponent(o.id);
export const workLink = (w: Work) => "/works/" + encodeURIComponent(w.id);
export const errorText = (err: unknown) =>
  err instanceof Error ? err.message : "暂时无法完成操作，请稍后重试。";

export function useStudio(sessionKey: unknown) {
  const [data, setData] = useState<Studio | null>(null);
  const [error, setError] = useState("");
  const serial = useRef(0);
  const load = useCallback(async () => {
    const current = ++serial.current;
    try {
      const next = await api<Studio>("/state");
      if (serial.current === current) {
        setData(next);
        setError("");
      }
      return next;
    } catch (err) {
      if (serial.current === current) setError(errorText(err));
      return null;
    }
  }, []);
  useEffect(() => {
    setData(null);
    void load();
    return () => {
      serial.current++;
    };
  }, [load, sessionKey]);
  const watching =
    !!data &&
    (data.works.some((w) => ["queued", "running"].includes(w.status)) ||
      data.orders.some(
        (o) =>
          ["queued", "running"].includes(o.generation_status) ||
          o.delivery_status === "review" ||
          o.payment_status === "refunding",
      ));
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible") void load();
    };
    window.addEventListener("focus", onVisible);
    document.addEventListener("visibilitychange", onVisible);
    const id = watching ? window.setInterval(onVisible, 3500) : undefined;
    return () => {
      window.clearInterval(id);
      window.removeEventListener("focus", onVisible);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [load, watching]);
  return { data, error, load };
}

export function useAction(refresh?: () => Promise<unknown>) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const locked = useRef(false);
  async function run<T>(
    action: () => Promise<T>,
    done?: (value: T) => void,
    message = "",
  ) {
    if (locked.current) return;
    locked.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const value = await action();
      if (refresh) await refresh();
      if (message) setNotice(message);
      done?.(value);
    } catch (err) {
      setError(errorText(err));
    } finally {
      locked.current = false;
      setBusy(false);
    }
  }
  return { busy, error, notice, run, setError };
}

export function useRequestKey() {
  const previous = useRef({ input: "", key: "" });
  return (input: unknown) => {
    const signature = JSON.stringify(input);
    if (signature !== previous.current.input) {
      const key =
        globalThis.crypto?.randomUUID?.() ??
        String(Date.now()) + "-" + Math.random().toString(36).slice(2);
      previous.current = { input: signature, key };
    }
    return previous.current.key;
  };
}

export function orderLabel(order: Order) {
  if (
    order.payment_status === "cancelled" ||
    order.status === "cancelled" ||
    order.delivery_status === "cancelled"
  )
    return "已取消";
  if (order.payment_status === "refunded") return "已退款";
  if (order.payment_status === "refunding") return "退款处理中";
  if (order.delivery_status === "needs_info") return "等待补充资料";
  if (order.payment_status === "unpaid") return "等待付款";
  if (order.delivery_status === "failed") return "等待恢复交付";
  if (order.delivery_status === "delivered") return "已交付";
  if (["failed", "uncertain"].includes(order.generation_status))
    return "等待客服跟进";
  if (order.kind === "model" && order.generation_status === "ready")
    return order.owner_confirmed ? "等待质检交付" : "等待你确认";
  if (order.kind === "model") return "正在建模";
  return "准备交付";
}
export const workLabel = (work: Work) =>
  ({
    queued: "等待制作",
    running: "正在制作",
    ready: "可以选稿",
    uncertain: "等待客服核实",
    failed: "未能完成",
  })[work.status] ?? "处理中";
export type StudioProps = {
  data: Studio;
  nav: Nav;
  refresh: () => Promise<unknown>;
};
