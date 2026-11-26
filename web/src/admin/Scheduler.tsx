import { useCallback, useEffect, useRef, useState } from "react";
import { Network, RefreshCw } from "lucide-react";
import { api } from "../common";
import { abbr, Blank, Tag } from "./shared";

const policies = {
  adaptive: "网络自适应",
  round_robin: "轮流分配",
  shortest_queue: "最短队列",
};
type Policy = keyof typeof policies;
interface NodeState {
  node_id: string;
  online: boolean;
  read_mbps: number;
  write_mbps: number;
  compute_s: number;
  queued: number;
  running: number;
  last_seen: number;
}
interface Task {
  job_id: string;
  target_id: string;
  status: string;
  node_id: string;
  input_bytes: number;
  epoch: number;
  estimate_s: number;
  reason: string;
  policy: Policy;
}
interface ScheduleEvent {
  job_id: string;
  node_id: string;
  epoch: number;
  at: number;
  detail: string;
  event: string;
}
interface Snapshot {
  enabled: boolean;
  policy: Policy;
  nodes: NodeState[];
  tasks: Task[];
  events: ScheduleEvent[];
}
const eventLabels: Record<string, string> = {
  enqueued: "进入队列", assigned: "分配任务", claimed: "开始处理", expired: "租约到期",
  completed: "提交结果", done: "已完成", failed: "执行失败", retry: "重新排队",
  stopped: "已停止", takeover: "故障接管",
};
const clock = (value: number) => new Date(value * 1000).toLocaleTimeString("zh-CN", {hour12: false});
const fixed = (value: number) => Number.isFinite(value) ? value.toFixed(2) : "—";

export default function Scheduler({ canChange }: { canChange: boolean }) {
  const [data, setData] = useState<Snapshot | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const sequence = useRef(0);
  const load = useCallback(async () => {
    const current = ++sequence.current;
    try {
      const value = await api<Snapshot>("/admin/scheduler");
      if (sequence.current === current) { setData(value); setError(""); }
    } catch (err) {
      if (sequence.current === current) setError((err as Error).message);
    }
  }, []);
  useEffect(() => {
    void load();
    const tick = () => { if (!document.hidden) void load(); };
    const timer = window.setInterval(tick, 3000);
    document.addEventListener("visibilitychange", tick);
    return () => {
      sequence.current++;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [load]);
  async function change(policy: string) {
    setSaving(true);
    try {
      await api("/admin/scheduler/policy", "POST", {policy});
      await load();
    } catch (err) { setError((err as Error).message); }
    finally { setSaving(false); }
  }
  return <div className="adm-scheduler">
    {error && <p className="adm-error" role="alert">{error}</p>}
    {!data ? <p>正在读取节点状态…</p> : <>
      <section className="adm-panel">
        <header><h3>工作节点</h3><button onClick={() => void load()}><RefreshCw size={15}/> 刷新</button></header>
        <div className="sched-controls">
          <span>{data.enabled ? "分布式处理" : "单机处理"} · {data.nodes.filter(n => n.online).length} 个在线节点</span>
          <label>调度策略 {canChange && data.enabled
            ? <select value={data.policy} disabled={saving} onChange={e => void change(e.target.value)}>
                {Object.entries(policies).map(([key, name]) => <option key={key} value={key}>{name}</option>)}
              </select> : <strong>{policies[data.policy]}</strong>}</label>
        </div>
        {data.nodes.length ? <div className="sched-nodes">{data.nodes.map(n => <article key={n.node_id}>
          <header><strong><Network size={16}/> {n.node_id}</strong><span className={n.online ? "sched-online" : ""}>{n.online ? "在线" : "离线"}</span></header>
          <dl>
            <dt>读取 / 写入</dt><dd>{fixed(n.read_mbps)} / {fixed(n.write_mbps)} MiB/s</dd>
            <dt>处理 / 排队</dt><dd>{n.running} / {n.queued} 单</dd>
            <dt>最近心跳</dt><dd>{clock(n.last_seen)}</dd>
          </dl>
        </article>)}</div> : <Blank>{data.enabled ? "等待工作节点连接到协调器" : "启用分布式处理后，这里会显示工作节点和链路速度。"}</Blank>}
      </section>
      <section className="adm-panel">
        <header><h3>任务分配</h3></header>
        {data.tasks.length ? <div className="sched-table"><table>
          <thead><tr><th>订单 / 模型大小</th><th>节点 / 租约版本</th><th>分配依据</th><th>状态</th></tr></thead>
          <tbody>{data.tasks.map(t => <tr key={t.job_id}>
            <td title={t.target_id}>{abbr(t.target_id)}<small>{fixed(t.input_bytes / 1048576)} MiB</small></td>
            <td>{t.node_id || "待分配"}{t.epoch > 0 && <small>第 {t.epoch} 版</small>}</td>
            <td>{t.node_id ? policies[t.policy] : "等待可用节点"}{t.node_id && <small>预计 {fixed(t.estimate_s)} 秒 · {t.reason}</small>}</td>
            <td><Tag value={t.status}/></td>
          </tr>)}</tbody>
        </table></div> : <Blank>模型进入后处理阶段后，可以在这里查看每笔订单的分配依据。</Blank>}
      </section>
      <section className="adm-panel">
        <header><h3>调度记录</h3></header>
        {data.events.length ? <ol className="sched-events">{data.events.map((e, i) =>
          <li key={e.job_id + ":" + e.at + ":" + i}><time>{clock(e.at)}</time><div>
            <strong>{eventLabels[e.event] || e.event}</strong> · {e.node_id || "协调器"} · {abbr(e.job_id)}
            {e.detail && <small>{e.detail}</small>}
          </div></li>)}</ol> : <Blank>暂无调度记录</Blank>}
      </section>
    </>}
  </div>;
}
