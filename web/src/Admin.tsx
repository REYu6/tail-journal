import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  Archive,
  Banknote,
  BarChart3,
  BellRing,
  BookOpen,
  Building2,
  ClipboardCheck,
  ClipboardList,
  Download,
  ExternalLink,
  History,
  LayoutDashboard,
  ListChecks,
  LockKeyhole,
  Network,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  UsersRound,
  Wallet,
  X,
} from "lucide-react";
import { api, money, type SessionUser } from "./common";
import {
  abbr,
  ActionDialog,
  Blank,
  Field,
  fmt,
  label,
  Tag,
  type Action,
  type Row,
} from "./admin/shared";
import Settings from "./admin/Settings";
import Channels from "./admin/Channels";
import Usage from "./admin/Usage";
import Scheduler from "./admin/Scheduler";
import "./admin.css";

type Props = {
  user: SessionUser | null;
  refreshUser: () => Promise<void>;
  navigate: (s: string) => void;
};
const pages = [
  ["overview", "经营概览", LayoutDashboard],
  ["orders", "订单与售后", ClipboardList],
  ["jobs", "生成任务", Activity],
  ["scheduler", "节点调度", Network],
  ["samples", "打样报价", Archive],
  ["people", "用户与档案", UsersRound],
  ["channels", "合作渠道", Building2],
  ["settings", "商品与画风", Settings2],
  ["audit", "操作记录", History],
] as const;
const issueOrder = (o: Row) =>
  o.support ||
  (o.payment_status === "paid" && o.delivery_status !== "delivered");
const modeLabels: Record<string, string> = {
  demo: "演示",
  live: "已接入",
  stripe: "Stripe",
};
function AdminLogin({ user, refreshUser, navigate }: Props) {
  const [email, setEmail] = useState(""),
    [password, setPassword] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <main className="admin-gate">
      <ShieldCheck size={38} />
      <h1>工作室管理</h1>
      <p>
        {user
          ? "请使用运营或管理员账号进入工作台。"
          : "用工作室账号登录，查看订单和交付进度。"}
      </p>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError("");
          try {
            await api("/auth/login", "POST", { email, password });
            await refreshUser();
            const state = await api("/state");
            if (!["admin", "operator"].includes(state.user?.role))
              setError("这个账号没有工作室管理权限。");
          } catch (x) {
            setError((x as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <Field title="工作室邮箱">
          <input
            type="email"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </Field>
        <Field title="密码">
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="current-password"
          />
        </Field>
        {error && (
          <p role="alert" className="adm-error">
            {error}
          </p>
        )}
        <button disabled={busy} className="adm-primary">
          {busy ? "正在登录…" : "进入管理后台"}
        </button>
      </form>
      <button className="adm-link" onClick={() => navigate("/")}>
        返回工作室首页
      </button>
    </main>
  );
}
export default function Admin(props: Props) {
  return !props.user || !["operator", "admin"].includes(props.user.role) ? (
    <AdminLogin {...props} />
  ) : (
    <Dashboard user={props.user} />
  );
}
function Dashboard({ user }: { user: SessionUser }) {
  const [data, S] = useState<Row | null>(null),
    [tab, T] = useState("overview"),
    [query, Q] = useState(""),
    [filter, F] = useState("all"),
    [err, E] = useState(""),
    [notice, N] = useState(""),
    [action, A] = useState<Action | null>(null),
    [busy, B] = useState(false),
    [expanded, Y] = useState(""),
    [petOpen, P] = useState("");
  const refreshToken = useRef(0);
  const load = useCallback(async () => {
    const t = ++refreshToken.current;
    try {
      const result = await api("/admin/state");
      if (t === refreshToken.current) {
        S(result);
        E("");
      }
    } catch (e) {
      if (t === refreshToken.current) E((e as Error).message);
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);
  useEffect(() => {
    if (tab === "settings" || tab === "scheduler") return;
    const timer = window.setInterval(() => {
      if (!document.hidden) void load();
    }, 12000);
    return () => clearInterval(timer);
  }, [load, tab]);
  function goto(k: string, f = "all") {
    T(k);
    Q("");
    F(f);
    Y("");
    P("");
    N("");
  }
  async function run(p: string, body: unknown = {}, method = "POST") {
    B(true);
    E("");
    N("");
    try {
      await api(p, method, body);
      await load();
      N("处理已保存");
      return true;
    } catch (e) {
      const msg = (e as Error).message;
      E(msg);
      return false;
    } finally {
      B(false);
    }
  }
  const admin = user.role === "admin";
  const arr = (key: string): Row[] => data?.[key] || [];
  const map = (items: Row[]) => Object.fromEntries(items.map((x) => [x.id, x]));
  const users = map(arr("users")),
    pets = map(arr("pets"));
  const orders = arr("orders"),
    jobs = arr("jobs"),
    samples = arr("samples");
  const matches = (...items: any[]) =>
    items.some((s) =>
      String(s || "")
        .toLowerCase()
        .includes(query.toLowerCase()),
    );
  const stats = data?.stats || {};
  const section = (k: string) =>
    pages.find((p) => p[0] === k)?.[1] || "管理后台";
  function cmd(
    title: string,
    path: string,
    field?: string,
    detail?: string,
    danger = false,
  ) {
    A({ title, field, detail, danger, submit: (note) => run(path, { note }) });
  }
  function retry(j: Row) {
    A({
      title: "恢复任务",
      detail: "优先使用原任务号查询或归档，重新提交可能再产生一次费用。",
      field: "原任务号或处理说明",
      optional: true,
      options: [
        { id: "resume", name: "恢复已有任务" },
        { id: "reconcile", name: "补录供应商任务号" },
        ...(admin ? [{ id: "new", name: "确认重新计费并生成" }] : []),
      ],
      submit: (note, _, mode) =>
        run("/admin/jobs/" + j.id + "/retry", {
          note,
          external_id: mode === "reconcile" ? note : "",
          confirm_resubmit: mode === "new",
        }),
    });
  }
  function orderCard(o: Row) {
    const open = expanded === o.id;
    const pet = pets[o.pet_id],
      owner = users[o.user_id];
    return (
      <article key={o.id} className="adm-record">
        <button
          className="adm-row-toggle"
          aria-expanded={open}
          onClick={() => Y(open ? "" : o.id)}
        >
          <span>
            <strong>
              {pet?.name || "宠物"} · {label[o.kind]}
            </strong>
            <small>
              {owner?.email} · {fmt(o.created_at)}
            </small>
          </span>
          <span className="adm-row-tags">
            <Tag value={o.payment_status} />
            <Tag value={o.delivery_status} />
            <b>¥{money(o.amount)}</b>
          </span>
        </button>
        {open && (
          <div className="adm-details">
            <p>
              订单号 <code>{o.id}</code>
            </p>
            <p>
              生成进度 <Tag value={o.generation_status} />
              　主人确认 {o.owner_confirmed ? "✓" : "—"}　运营质检{" "}
              {o.quality_checked ? "✓" : "—"}
            </p>
            {o.feedback && <p>主人修改意见　{o.feedback}</p>}
            {o.support && <p className="adm-callout">售后留言　{o.support}</p>}
            {o.support_reply && <p>处理回复　{o.support_reply}</p>}
            {o.error && <p role="alert">{o.error}</p>}
            {o.kind === "portrait" && o.preview_url && (
              <a
                className="adm-link"
                href={o.preview_url}
                target="_blank"
                rel="noreferrer"
              >
                查看选定版本 <ExternalLink size={14} />
              </a>
            )}
            <div className="adm-actions">
              {o.kind === "model" &&
                o.generation_status === "ready" &&
                o.payment_status === "paid" && (
                  <>
                    <a href={"/api/media/glb/" + o.id}>
                      <Download size={15} />
                      GLB
                    </a>
                    <a href={"/api/media/stl/" + o.id}>
                      <Download size={15} />
                      STL
                    </a>
                    {!o.quality_checked && (
                      <button
                        onClick={() =>
                          cmd(
                            "通过质检",
                            "/admin/orders/" + o.id + "/qc",
                            "切片检查结果",
                            "请先检查当前版本的 GLB 与 STL。",
                          )
                        }
                      >
                        记录质检
                      </button>
                    )}
                  </>
                )}
              {o.kind === "model" &&
                ["unpaid", "paid"].includes(o.payment_status) &&
                !["delivered", "needs_info"].includes(o.delivery_status) &&
                !["queued", "running", "uncertain"].includes(
                  o.generation_status,
                ) && (
                  <button
                    onClick={() =>
                      cmd(
                        "请求补图",
                        "/admin/orders/" + o.id + "/request-photos",
                        "需要补拍的角度或特征",
                        "主人会在原订单看到这条说明。",
                      )
                    }
                  >
                    请主人补图
                  </button>
                )}
              {o.payment_status === "paid" && (
                <button
                  onClick={() =>
                    cmd(
                      "恢复原件",
                      "/admin/orders/" + o.id + "/restore",
                      undefined,
                      "从已归档的作品恢复交付。",
                    )
                  }
                >
                  恢复交付
                </button>
              )}
              {o.support && (
                <button
                  onClick={() =>
                    cmd(
                      "回复售后",
                      "/admin/orders/" + o.id + "/resolve",
                      "给主人回复",
                    )
                  }
                >
                  处理售后
                </button>
              )}
              {admin && ["paid", "refunding"].includes(o.payment_status) && (
                <button
                  className="adm-warn"
                  onClick={() =>
                    cmd(
                      "退款",
                      "/admin/orders/" + o.id + "/refund",
                      "退款原因",
                      "整单退款，退款完成后收回文件下载权限。",
                      true,
                    )
                  }
                >
                  退款
                </button>
              )}
            </div>
          </div>
        )}
      </article>
    );
  }
  const summaryCards = [
    [Banknote, "已收款净额", "¥" + money(stats.revenue || 0), "orders"],
    [Wallet, "已付款订单", stats.paid_orders || 0, "orders"],
    [ClipboardCheck, "待交付", stats.pending_delivery || 0, "orders"],
    [BellRing, "待恢复任务", stats.failed_jobs || 0, "jobs"],
  ] as const;
  return (
    <main className="admin-layout">
      <aside className="adm-aside">
        <div>
          <ShieldCheck size={22} />
          <strong>运营工作台</strong>
        </div>
        <nav>
          {pages
            .filter((p) => admin || p[0] !== "settings")
            .map(([key, n, Icon]) => (
              <button
                className={tab === key ? "selected" : ""}
                onClick={() => goto(key)}
                key={key}
              >
                <Icon size={17} />
                {n}
              </button>
            ))}
        </nav>
        <small>
          <LockKeyhole size={13} />
          {label[user.role]} · {user.name}
        </small>
      </aside>
      <section className="adm-main">
        <header className="adm-heading">
          <div>
            <p>尾巴手记 / 工作室管理</p>
            <h1>{section(tab)}</h1>
          </div>
          {tab !== "scheduler" && <button disabled={busy} onClick={() => void load()}>
            <RefreshCw size={15} />
            刷新
          </button>}
        </header>
        {err && (
          <p role="alert" className="adm-error">
            {err}
          </p>
        )}
        {notice && (
          <div role="status" className="adm-notice">
            {notice}
            <button aria-label="关闭提示" onClick={() => N("")}>
              <X size={14} />
            </button>
          </div>
        )}
        {!data && !err && <p>正在读取工作台…</p>}
        {data && (
          <>
            {tab === "overview" ? (
              <>
                <div className="adm-status">
                  <span>当前接入</span>
                  {[
                    ["images", "肖像"],
                    ["models", "3D"],
                    ["payments", "支付"],
                  ].map(([k, v]) => (
                    <span key={k}>
                      {v} · {modeLabels[data.mode[k]] || data.mode[k]}
                    </span>
                  ))}
                </div>
                <div className="adm-metrics">
                  {summaryCards.map(([Icon, n, v, key]) => (
                    <button
                      key={n}
                      onClick={() =>
                        goto(
                          key,
                          n === "待交付"
                            ? "attention"
                            : n === "待恢复任务"
                              ? "failed"
                              : "all",
                        )
                      }
                    >
                      <Icon size={20} />
                      <span>{n}</span>
                      <b>{v}</b>
                    </button>
                  ))}
                </div>
                <section className="adm-panel">
                  <header>
                    <h3>需要跟进的订单</h3>
                    <button onClick={() => goto("orders", "attention")}>
                      查看全部
                    </button>
                  </header>
                  {orders.filter(issueOrder).length ? (
                    orders.filter(issueOrder).slice(0, 5).map(orderCard)
                  ) : (
                    <Blank>当前没有待跟进的订单</Blank>
                  )}
                </section>
                <Usage data={data} />
              </>
            ) : tab === "scheduler" ? (
              <Scheduler canChange={admin} />
            ) : tab === "settings" ? (
              <Settings
                data={data}
                run={run}
                userId={String(user.id)}
                refresh={load}
              />
            ) : (
              <section className="adm-panel">
                <div className="adm-toolbar">
                  <label className="adm-search">
                    <Search size={16} />
                    <input
                      aria-label="搜索当前列表"
                      placeholder={
                        tab === "orders"
                          ? "搜索订单、主人或宠物"
                          : "搜索当前列表"
                      }
                      value={query}
                      onChange={(e) => Q(e.target.value)}
                    />
                  </label>
                  {["jobs", "orders"].includes(tab) && (
                    <label className="adm-filter">
                      <SlidersHorizontal size={15} />
                      <select
                        aria-label="状态筛选"
                        value={filter}
                        onChange={(e) => F(e.target.value)}
                      >
                        <option value="all">全部状态</option>
                        {tab === "orders" ? (
                          <>
                            <option value="attention">待跟进</option>
                            <option value="refunded">已退款</option>
                            <option value="delivered">已交付</option>
                          </>
                        ) : (
                          <option value="failed">待恢复</option>
                        )}
                      </select>
                    </label>
                  )}
                </div>
                {tab === "orders" &&
                  (() => {
                    const rows = orders.filter(
                      (o) =>
                        matches(
                          o.id,
                          users[o.user_id]?.email,
                          pets[o.pet_id]?.name,
                        ) &&
                        (filter === "all" ||
                          (filter === "attention" && issueOrder(o)) ||
                          o.payment_status === filter ||
                          o.delivery_status === filter),
                    );
                    return rows.length ? (
                      rows.map(orderCard)
                    ) : (
                      <Blank>没有符合条件的订单</Blank>
                    );
                  })()}
                {tab === "jobs" &&
                  (() => {
                    const rows = jobs.filter(
                      (j) =>
                        matches(
                          j.id,
                          j.target_id,
                          j.external_id,
                          j.error,
                          label[j.kind],
                          label[j.status],
                        ) &&
                        (filter === "all" ||
                          ["failed", "uncertain"].includes(j.status)),
                    );
                    return rows.length ? (
                      rows.map((j) => (
                        <article className="adm-record adm-pad" key={j.id}>
                          <header>
                            <strong>{label[j.kind]}</strong>
                            <Tag value={j.status} />
                          </header>
                          <p>
                            <code>{j.id}</code> · {fmt(j.created_at)}
                          </p>
                          {j.external_id && (
                            <p>
                              供应商任务　<code>{j.external_id}</code>
                            </p>
                          )}
                          {j.error && <p className="adm-callout">{j.error}</p>}
                          {["failed", "uncertain"].includes(j.status) && (
                            <button onClick={() => retry(j)}>处理任务</button>
                          )}
                        </article>
                      ))
                    ) : (
                      <Blank>当前没有符合条件的生成任务</Blank>
                    );
                  })()}
                {tab === "samples" &&
                  (() => {
                    const rows = samples.filter((x) =>
                      matches(
                        x.id,
                        x.order_id,
                        x.specs,
                        x.note,
                        users[x.user_id]?.email,
                      ),
                    );
                    return rows.length ? (
                      rows.map((s) => (
                        <article className="adm-record adm-pad" key={s.id}>
                          <header>
                            <strong>{users[s.user_id]?.name}的打样申请</strong>
                            <Tag value={s.status} />
                          </header>
                          <p>{s.specs}</p>
                          <p>
                            订单 <code>{s.order_id}</code>
                          </p>
                          {s.quote != null && (
                            <p>
                              报价 ¥{money(s.quote)}　{s.note}
                            </p>
                          )}
                          {["requested", "quoted"].includes(s.status) && (
                            <button
                              onClick={() =>
                                A({
                                  title: "发送报价",
                                  field: "材质、尺寸和预计交期",
                                  amount: true,
                                  submit: (note, amount) =>
                                    run("/admin/samples/" + s.id + "/quote", {
                                      quote: Math.round(Number(amount) * 100),
                                      note,
                                    }),
                                })
                              }
                            >
                              填写报价
                            </button>
                          )}
                        </article>
                      ))
                    ) : (
                      <Blank>暂无打样申请</Blank>
                    );
                  })()}
                {tab === "people" &&
                  (() => {
                    const rows = arr("users").filter((u) =>
                      matches(
                        u.name,
                        u.email,
                        ...arr("pets")
                          .filter((p) => p.user_id === u.id)
                          .map((p) => p.name),
                      ),
                    );
                    return rows.length ? (
                      rows.map((u) => (
                        <article key={u.id} className="adm-record">
                          <button
                            className="adm-row-toggle"
                            onClick={() => {
                              Y(expanded === u.id ? "" : u.id);
                              P("");
                            }}
                          >
                            <span>
                              <strong>{u.name}</strong>
                              <small>{u.email}</small>
                            </span>
                            <Tag value={u.role} />
                          </button>
                          {expanded === u.id && (
                            <div className="adm-details">
                              {admin && String(u.id) !== String(user.id) && (
                                <button
                                  onClick={() =>
                                    A({
                                      title: "更改权限",
                                      detail: u.email,
                                      options: [
                                        "owner",
                                        "operator",
                                        "admin",
                                      ].map((k) => ({ id: k, name: label[k] })),
                                      submit: (_, __, role) =>
                                        run("/admin/users/" + u.id + "/role", {
                                          role,
                                        }),
                                    })
                                  }
                                >
                                  更改权限
                                </button>
                              )}
                              {arr("pets")
                                .filter((p) => p.user_id === u.id)
                                .map((p) => (
                                  <div className="adm-pet" key={p.id}>
                                    <strong>{p.name}</strong>　{p.traits}
                                    <button
                                      onClick={() =>
                                        P(petOpen === p.id ? "" : p.id)
                                      }
                                    >
                                      {petOpen === p.id
                                        ? "收起原照"
                                        : "查看原照（将留存记录）"}
                                    </button>
                                    {petOpen === p.id && (
                                      <div className="adm-photos">
                                        {p.photos.map((ph: Row) => (
                                          <a
                                            key={ph.id}
                                            href={ph.url}
                                            target="_blank"
                                            rel="noreferrer"
                                          >
                                            <img src={ph.url} alt={ph.name} />
                                          </a>
                                        ))}
                                      </div>
                                    )}
                                  </div>
                                ))}
                            </div>
                          )}
                        </article>
                      ))
                    ) : (
                      <Blank>没有找到用户</Blank>
                    );
                  })()}
                {tab === "channels" && (
                  <Channels
                    rows={arr("channels")}
                    admin={admin}
                    query={query}
                    run={run}
                  />
                )}
                {tab === "audit" &&
                  (() => {
                    const rows = arr("audit").filter((x) =>
                      matches(
                        x.actor,
                        x.action,
                        x.target,
                        x.note,
                        users[x.actor]?.email,
                      ),
                    );
                    return rows.length ? (
                      rows.map((x) => (
                        <article className="adm-record adm-pad" key={x.id}>
                          <header>
                            <strong>{auditLabel[x.action] || x.action}</strong>
                            <small>{fmt(x.created_at)}</small>
                          </header>
                          <p>
                            {users[x.actor]?.email || abbr(x.actor)} ·{" "}
                            <code>{x.target}</code>
                          </p>
                          {x.note && <p>{x.note}</p>}
                        </article>
                      ))
                    ) : (
                      <Blank>暂无相关操作记录</Blank>
                    );
                  })()}
              </section>
            )}
          </>
        )}
      </section>
      {action && <ActionDialog action={action} onClose={() => A(null)} />}
    </main>
  );
}
const auditLabel: Record<string, string> = {
  settings_updated: "更新工作室设置",
  role_changed: "修改人员权限",
  model_qc_passed: "模型质检通过",
  delivery_recovered: "恢复文件交付",
  support_resolved: "处理售后留言",
  sample_quoted: "发送打样报价",
  job_reconciled: "恢复已有任务",
  scheduler_policy: "调整调度策略",
  postprocess_retry: "重试模型后处理",
  model_resubmitted: "重新提交生成",
  refund_succeeded: "订单已退款",
  refund_pending: "等待支付退款",
  staff_media_access: "查看私有素材",
};
