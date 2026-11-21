import { createElement, useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  Box,
  Check,
  ChevronRight,
  CircleCheck,
  Download,
  Images,
  LifeBuoy,
  PackageCheck,
  Expand,
  RotateCcw,
  ShoppingBag,
} from "lucide-react";
import {
  api,
  dateText,
  money,
  modelLink,
  orderLabel,
  orderLink,
  petLink,
  same,
  useAction,
  type Id,
  type Order,
  type StudioProps,
} from "./data";
import { AlbumReceipt, AlbumViewer } from "./AlbumViewer";
import {
  Blank,
  Confirm,
  DemoNote,
  Entry,
  Note,
  RefreshButton,
  SummaryImage,
  Wait,
} from "./ui";

function ModelView({ url }: { url: string }) {
  const [ready, setReady] = useState(false),
    [failed, setFailed] = useState(false);
  const node = useRef<HTMLElement | null>(null);
  useEffect(() => {
    let active = true;
    void import("@google/model-viewer")
      .then(() => {
        if (active) setReady(true);
      })
      .catch(() => {
        if (active) setFailed(true);
      });
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    if (!node.current) return;
    const current = node.current;
    const onError = () => setFailed(true);
    current.addEventListener("error", onError);
    return () => current.removeEventListener("error", onError);
  }, [ready, url]);
  return (
    <div className="ow-model-stage">
      {failed ? (
        <div className="ow-missing">
          <Box size={26} />
          当前浏览器没有成功载入 3D 预览。
          <button
            className="ow-link"
            onClick={() => {
              setFailed(false);
              setReady(false);
              void import("@google/model-viewer")
                .then(() => setReady(true))
                .catch(() => setFailed(true));
            }}
          >
            重新加载
          </button>
        </div>
      ) : ready ? (
        createElement("model-viewer", {
          ref: node,
          src: url,
          alt: "可旋转查看的宠物立体模型",
          "camera-controls": true,
          "touch-action": "pan-y",
          "shadow-intensity": "0.8",
          "interaction-prompt": "none",
          exposure: "1",
          style: { width: "100%", height: "100%" },
        })
      ) : (
        <Wait label="正在准备 3D 预览…" />
      )}
      {!failed && (
        <small>
          <RotateCcw size={13} />
          拖动旋转 · 双指缩放
        </small>
      )}
    </div>
  );
}
const sampleLabels: Record<string, string> = {
  requested: "等待运营报价",
  pending: "等待运营报价",
  quoted: "等待你确认报价",
  accepted: "已接受报价",
  declined: "已婉拒报价",
  rejected: "已婉拒报价",
  closed: "已结束",
};
export function OrderList({ data, nav, refresh }: StudioProps) {
  const [filter, setFilter] = useState("all");
  const filtered = data.orders.filter(
    (o) =>
      filter === "all" ||
      (filter === "active"
        ? !["已交付", "已取消", "已退款"].includes(orderLabel(o))
        : o.delivery_status === "delivered"),
  );
  return (
    <Entry
      title="我的订单"
      intro="查看付款、制作和交付进度。"
      action={<RefreshButton refresh={refresh} />}
    >
      <div className="ow-tabs ow-filter" aria-label="筛选订单">
        {[
          ["all", "全部"],
          ["active", "处理中"],
          ["delivered", "已交付"],
        ].map(([v, s]) => (
          <button
            key={v}
            className={v === filter ? "is-current" : ""}
            onClick={() => setFilter(v)}
          >
            {s}
          </button>
        ))}
      </div>
      {!filtered.length ? (
        <Blank
          icon={<ShoppingBag size={32} />}
          title={data.orders.length ? "当前没有这类订单" : "还没有订单"}
          text={
            data.orders.length
              ? "切换筛选可以查看其他记录。"
              : "从它的档案出发，选中满意的肖像或制作立体模型。"
          }
          action={() => (data.orders.length ? setFilter("all") : nav("/pets"))}
          label={data.orders.length ? "查看全部订单" : "查看宠物档案"}
        />
      ) : (
        <div className="ow-order-list">
          {filtered.map((o) => {
            const pet = data.pets.find((p) => same(p.id, o.pet_id));
            return (
              <button
                key={o.id}
                className="ow-order-row"
                onClick={() => nav(orderLink(o))}
              >
                <div className="ow-order-icon">
                  {o.kind === "portrait" && o.preview_url ? (
                    <img src={o.preview_url} alt="所选作品" />
                  ) : pet ? (
                    <SummaryImage pet={pet} />
                  ) : (
                    <Box size={22} />
                  )}
                </div>
                <span className="ow-order-subject">
                  <strong>
                    {pet?.name ?? "宠物"}的
                    {o.kind === "model" ? " 3D 模型" : "纪念肖像"}
                  </strong>
                  <small>{dateText(o.created_at)}</small>
                </span>
                <span className="ow-status">{orderLabel(o)}</span>
                <strong>{money(o.amount)}</strong>
                <ChevronRight size={17} />
              </button>
            );
          })}
        </div>
      )}
    </Entry>
  );
}
export function OrderDetail({
  order,
  data,
  nav,
  refresh,
}: StudioProps & { order: Order }) {
  const [feedback, setFeedback] = useState(""),
    [support, setSupport] = useState(""),
    [specs, setSpecs] = useState("");
  const [revision, setRevision] = useState(false),
    [help, setHelp] = useState(false),
    [sampling, setSampling] = useState(false);
  const [newPhotos, setNewPhotos] = useState<string[]>([]);
  const [supplementPhotos, setSupplementPhotos] = useState<string[]>([]),
    [supplementConsent, setSupplementConsent] = useState(false);
  const [requestsSent, setRequestsSent] = useState(false);
  const action = useAction(refresh);
  const pet = data.pets.find((p) => same(p.id, order.pet_id));
  const model = order.kind === "model";
  const label = orderLabel(order),
    paid = order.payment_status === "paid",
    ready = order.generation_status === "ready",
    delivered = order.delivery_status === "delivered" && paid;
  const sample = data.samples.find((s) => same(s.order_id, order.id));
  const route = "/orders/" + order.id;
  const activeHold =
    ["unpaid", "paid"].includes(order.payment_status) &&
    !["cancelled", "refunded"].includes(order.delivery_status);
  const paidPhoto = order.downloads?.find((d) => /jpg|png|肖像/i.test(d.name));
  const picture = !model ? paidPhoto?.url || order.preview_url : undefined;
  function pay() {
    void action.run(
      () =>
        api<{ checkout_url?: string; order: Order; demo?: boolean }>(
          route + "/pay",
          "POST",
        ),
      (r) => {
        if (r.checkout_url) {
          window.location.assign(r.checkout_url);
        }
      },
    );
  }
  return (
    <Entry
      title={(pet?.name ?? "宠物") + (model ? "的 3D 模型" : "的纪念肖像")}
      back={["全部订单", () => nav("/orders")]}
      action={<RefreshButton refresh={refresh} />}
    >
      <div className="ow-order-layout">
        <div>
          {model && order.preview_url ? (
            <ModelView
              key={order.preview_url + "-" + (order.revision_count ?? 0)}
              url={order.preview_url}
            />
          ) : picture ? (
            <div className="ow-order-art">
              <img src={picture} alt="订单对应的纪念肖像" />
            </div>
          ) : (
            <div className="ow-order-art ow-order-ref">
              {pet?.photos[0] ? (
                <img src={pet.photos[0].url} alt="宠物档案原照" />
              ) : (
                <Box size={48} />
              )}
              <small>档案参考图</small>
            </div>
          )}
        </div>
        <section className="ow-panel ow-order-summary">
          <span className="ow-status">{label}</span>
          <h2>{model ? "立体纪念模型" : "高清纪念肖像"}</h2>
          <p>
            {model
              ? "GLB 旋转预览与 STL 打印文件，待你确认外观并通过质检后交付。"
              : "付款后领取选定版本的高清无水印作品，保存在你的私人相册。"}
          </p>
          <div className="ow-kv">
            <span>订单金额</span>
            <strong>{money(order.amount)}</strong>
          </div>
          <div className="ow-kv">
            <span>创建日期</span>
            <span>{dateText(order.created_at)}</span>
          </div>
          <div className="ow-kv">
            <span>订单号</span>
            <span className="ow-code">{order.id}</span>
          </div>
          {order.payment_status === "unpaid" &&
            order.delivery_status !== "needs_info" &&
            activeHold && (
              <>
                <DemoNote data={data} kind="payments" />
                <button className="ow-btn" disabled={action.busy} onClick={pay}>
                  {action.busy
                    ? "正在处理…"
                    : String(data.mode.payments).toLowerCase() === "demo"
                      ? "确认演示付款"
                      : "去付款"}{" "}
                  · {money(order.amount)}
                  <ArrowRight size={16} />
                </button>
                <Confirm
                  label="取消订单"
                  prompt="确定取消这笔待付订单？"
                  disabled={action.busy}
                  onYes={() =>
                    void action.run(
                      () => api(route + "/cancel", "POST"),
                      undefined,
                      "订单已取消。",
                    )
                  }
                />
              </>
            )}
          {paid && model && <DemoNote data={data} kind="models" />}
          {model &&
            paid &&
            ready &&
            order.preview_url &&
            !delivered &&
            order.delivery_status !== "needs_info" && (
              <div className="ow-form">
                {!order.owner_confirmed ? (
                  <>
                    <button
                      disabled={action.busy}
                      className="ow-btn"
                      onClick={() =>
                        void action.run(
                          () => api(route + "/confirm", "POST"),
                          undefined,
                          "已记录你的外观确认。",
                        )
                      }
                    >
                      <Check size={16} />
                      我确认这个造型
                    </button>
                    {(order.revision_count ?? 0) < 1 && (
                      <button
                        className="ow-btn ow-secondary"
                        disabled={action.busy}
                        onClick={() => setRevision((v) => !v)}
                      >
                        提出一次修改
                      </button>
                    )}
                  </>
                ) : (
                  <p className="ow-tip">
                    <CircleCheck size={17} />
                    你已确认造型。
                  </p>
                )}
                <p className="ow-subtle">
                  文件质检：{order.quality_checked ? "已通过" : "等待运营核对"}
                </p>
              </div>
            )}
          <AlbumReceipt delivered={delivered} nav={nav} />
          {delivered && (
            <div className="ow-form">
              {order.downloads.map((d) => (
                <a
                  className="ow-btn"
                  key={d.url}
                  href={d.url}
                  download={d.name}
                >
                  <Download size={16} />
                  下载{d.name}
                </a>
              ))}
              {!model && pet && order.candidate_id && (
                <button
                  className="ow-btn ow-secondary"
                  onClick={() =>
                    nav(
                      modelLink(pet) +
                        "&candidate=" +
                        encodeURIComponent(order.candidate_id!),
                    )
                  }
                >
                  <Box size={16} />
                  用这幅肖像做 3D
                </button>
              )}
            </div>
          )}
          {model &&
            paid &&
            order.delivery_status !== "needs_info" &&
            ["running", "queued", "pending"].includes(
              order.generation_status,
            ) && <Wait label="模型正在制作，可以稍后回来。" />}
          {["failed", "uncertain"].includes(order.generation_status) && (
            <Note
              error={
                order.error || "制作遇到问题，请通过下方售后入口联系运营核实。"
              }
            />
          )}
          {order.payment_status === "refunded" && (
            <p className="ow-subtle">该订单已退款，作品下载已关闭。</p>
          )}
        </section>
      </div>
      <Note error={action.error} notice={action.notice} />
      {order.delivery_status === "needs_info" && model && pet && (
        <form
          className="ow-panel ow-form ow-spaced"
          onSubmit={(e) => {
            e.preventDefault();
            void action.run(
              () =>
                api(route + "/supplement", "POST", {
                  photo_ids: supplementPhotos,
                  accept_inference: supplementConsent,
                }),
              () => {
                setSupplementPhotos([]);
                setSupplementConsent(false);
              },
              "资料已补充，将继续原订单。",
            );
          }}
        >
          <h2>补充建模资料</h2>
          <p>
            {order.supplement_note ||
              "请补充清晰的参考角度，以便运营继续建模。"}
          </p>
          <div className="ow-picks">
            {pet.photos.map((p) => {
              const id = String(p.id),
                selected = supplementPhotos.includes(id);
              return (
                <button
                  type="button"
                  key={id}
                  disabled={!selected && supplementPhotos.length >= 4}
                  className={"ow-pick " + (selected ? "is-current" : "")}
                  aria-label={"选择 " + p.name}
                  aria-pressed={selected}
                  onClick={() => {
                    setSupplementPhotos((ids) =>
                      selected ? ids.filter((v) => v !== id) : [...ids, id],
                    );
                    setSupplementConsent(false);
                  }}
                >
                  <img src={p.url} alt={p.name} />
                  <span className="ow-check">
                    {selected && <Check size={13} />}
                  </span>
                </button>
              );
            })}
          </div>
          <button
            type="button"
            className="ow-link"
            onClick={() => nav(petLink(pet))}
          >
            前往档案上传新照片
          </button>
          {supplementPhotos.length === 1 && (
            <label className="ow-checkbox">
              <input
                type="checkbox"
                required
                checked={supplementConsent}
                onChange={(e) => setSupplementConsent(e.target.checked)}
              />
              同意对未拍到的部位进行推测补全
            </label>
          )}
          <button
            className="ow-btn"
            disabled={action.busy || !supplementPhotos.length}
          >
            提交资料，继续原单
          </button>
        </form>
      )}
      {(order.support || order.support_reply) && (
        <section className="ow-panel ow-spaced">
          <h2>售后记录</h2>
          {order.support && <p>你的反馈：{order.support}</p>}
          <p>
            {order.support_reply
              ? "运营回复：" + order.support_reply
              : "运营正在查看这笔反馈。"}
          </p>
        </section>
      )}

      {revision && !order.owner_confirmed && !delivered && (
        <form
          className="ow-panel ow-form ow-spaced"
          onSubmit={(e) => {
            e.preventDefault();
            if (!feedback.trim()) return;
            void action.run(
              () =>
                api(route + "/revise", "POST", {
                  feedback: feedback.trim(),
                  ...(newPhotos.length ? { photo_ids: newPhotos } : {}),
                }),
              () => {
                setRevision(false);
                setNewPhotos([]);
              },
              "修改已提交，制作完成后可再次确认。",
            );
          }}
        >
          <label>
            希望调整哪里？
            <textarea
              required
              value={feedback}
              maxLength={1000}
              onChange={(e) => setFeedback(e.target.value)}
              rows={3}
              placeholder="例如尾巴的方向、耳朵或姿势。"
            />
          </label>
          {!!pet?.photos.length && (
            <fieldset>
              <legend>
                补充或更换参考照片 <small>选填，最多 4 张</small>
              </legend>
              <div className="ow-picks">
                {pet.photos.map((p) => {
                  const id = String(p.id),
                    selected = newPhotos.includes(id);
                  return (
                    <button
                      type="button"
                      key={id}
                      disabled={!selected && newPhotos.length >= 4}
                      className={"ow-pick " + (selected ? "is-current" : "")}
                      aria-label={"选择 " + p.name}
                      aria-pressed={selected}
                      onClick={() =>
                        setNewPhotos((ids) =>
                          selected ? ids.filter((v) => v !== id) : [...ids, id],
                        )
                      }
                    >
                      <img src={p.url} alt={p.name} />
                      <span className="ow-check">
                        {selected && <Check size={13} />}
                      </span>
                    </button>
                  );
                })}
              </div>
            </fieldset>
          )}
          <button className="ow-btn" disabled={action.busy || !feedback.trim()}>
            提交修改
          </button>
        </form>
      )}
      {model && delivered && (
        <section className="ow-panel ow-spaced">
          <h2>
            <PackageCheck size={20} />
            实体打样
          </h2>
          {sample ? (
            <>
              <p>
                {sampleLabels[sample.status] ?? sample.status} · {sample.specs}
              </p>
              {sample.quote !== null &&
                sample.quote !== undefined &&
                (typeof sample.quote === "number"
                  ? sample.quote > 0
                  : String(sample.quote).trim()) && (
                  <p>
                    运营报价：
                    {typeof sample.quote === "number"
                      ? money(sample.quote)
                      : sample.quote}
                  </p>
                )}
              {sample.note && <p>{sample.note}</p>}
              {sample.status === "quoted" && (
                <div className="ow-actions">
                  <button
                    className="ow-btn"
                    disabled={action.busy}
                    onClick={() =>
                      void action.run(
                        () =>
                          api("/samples/" + sample.id + "/respond", "POST", {
                            accept: true,
                          }),
                        undefined,
                        "已接受报价，运营将联系你确认后续安排。",
                      )
                    }
                  >
                    接受报价
                  </button>
                  <button
                    className="ow-btn ow-secondary"
                    disabled={action.busy}
                    onClick={() =>
                      void action.run(
                        () =>
                          api("/samples/" + sample.id + "/respond", "POST", {
                            accept: false,
                          }),
                        undefined,
                        "已记录你的选择。",
                      )
                    }
                  >
                    暂不制作
                  </button>
                </div>
              )}
            </>
          ) : (
            <>
              <p>
                想把模型做成摆件？告诉运营你的尺寸、材质与颜色偏好，收到报价后再决定。
              </p>
              {!sampling ? (
                <button
                  className="ow-btn ow-secondary"
                  onClick={() => setSampling(true)}
                >
                  申请实体打样
                </button>
              ) : (
                <form
                  className="ow-form"
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (!specs.trim()) return;
                    void action.run(
                      () =>
                        api(route + "/sample", "POST", { specs: specs.trim() }),
                      () => setSampling(false),
                      "打样申请已送达。",
                    );
                  }}
                >
                  <label>
                    期望的规格
                    <textarea
                      required
                      rows={2}
                      maxLength={1000}
                      value={specs}
                      onChange={(e) => setSpecs(e.target.value)}
                      placeholder="例如 8 厘米，全彩，带底座。"
                    />
                  </label>
                  <button
                    className="ow-btn"
                    disabled={action.busy || !specs.trim()}
                  >
                    提交申请
                  </button>
                </form>
              )}
            </>
          )}
        </section>
      )}
      <section className="ow-support ow-spaced">
        <button className="ow-link" onClick={() => setHelp((v) => !v)}>
          <LifeBuoy size={16} />
          {help ? "收起售后" : "这笔订单需要帮助"}
        </button>
        {help && (
          <form
            className="ow-panel ow-form ow-spaced"
            onSubmit={(e) => {
              e.preventDefault();
              if (!support.trim()) return;
              void action.run(
                () =>
                  api(route + "/support", "POST", { message: support.trim() }),
                () => {
                  setRequestsSent(true);
                  setSupport("");
                },
                "售后反馈已提交。",
              );
            }}
          >
            <label>
              发生了什么？
              <textarea
                rows={3}
                required
                maxLength={1000}
                value={support}
                onChange={(e) => setSupport(e.target.value)}
                placeholder="例如付款后无法打开文件。"
              />
            </label>
            <button
              className="ow-btn"
              disabled={action.busy || !support.trim()}
            >
              发送给运营
            </button>
            {(requestsSent || order.support) && (
              <p className="ow-subtle">运营可以通过这笔订单看到反馈并跟进。</p>
            )}
          </form>
        )}
      </section>
    </Entry>
  );
}
export function Album({ data, nav }: StudioProps) {
  const [filter, setFilter] = useState("all");
  const [viewing, setViewing] = useState<Id | null>(null);
  const delivered = data.orders.filter(
    (o) => o.payment_status === "paid" && o.delivery_status === "delivered",
  );
  const items = delivered.filter((o) => filter === "all" || o.kind === filter);
  const portraits = items.filter((o) => o.kind === "portrait");
  const open = viewing !== null && portraits.some((o) => same(o.id, viewing));
  return (
    <Entry
      title="纪念相册"
      intro="每一份已经定稿的作品，都和它的故事放在一起。"
    >
      <div className="ow-album-filters">
        <div
          className="ow-tabs ow-filter"
          role="group"
          aria-label="筛选纪念作品"
        >
          {[
            ["all", "全部作品"],
            ["portrait", "纪念肖像"],
            ["model", "立体模型"],
          ].map(([v, s]) => (
            <button
              key={v}
              className={filter === v ? "is-current" : ""}
              aria-pressed={filter === v}
              onClick={() => setFilter(v)}
            >
              {s}
            </button>
          ))}
        </div>
        <small role="status">{items.length} 份作品</small>
      </div>
      {!items.length ? (
        <Blank
          icon={<Images size={32} />}
          title={
            delivered.length
              ? "这里暂时没有这一类作品"
              : "等第一份纪念作品来到这里"
          }
          text={
            delivered.length
              ? "可以在其他分类找到已交付的作品。"
              : "选中一张满意的肖像，或者完成一件 3D 模型，交付后都能在这里重新打开和下载。"
          }
          action={() => (delivered.length ? setFilter("all") : nav("/pets"))}
          label={delivered.length ? "查看全部作品" : "去宠物档案"}
        />
      ) : (
        <div key={filter} className="ow-cardgrid ow-album-grid">
          {items.map((o) => {
            const p = data.pets.find((p) => same(p.id, o.pet_id));
            return (
              <button
                key={o.id}
                className="ow-pet-card"
                aria-haspopup={o.kind === "portrait" ? "dialog" : undefined}
                onClick={(event) => {
                  if (o.kind === "portrait") {
                    event.currentTarget.focus({ preventScroll: true });
                    setViewing(o.id);
                  } else nav(orderLink(o));
                }}
              >
                <div className="ow-card-cover">
                  {o.kind === "portrait" ? (
                    <>
                      <img
                        loading="lazy"
                        src={o.downloads[0]?.url ?? o.preview_url}
                        alt={"纪念肖像 · " + (p?.name ?? "")}
                      />
                      <span className="ow-card-tag">
                        <Expand size={13} />
                        翻阅肖像
                      </span>
                    </>
                  ) : (
                    <>
                      {p ? <SummaryImage pet={p} /> : <Box />}
                      <span className="ow-card-tag">
                        <Box size={14} />
                        立体模型
                      </span>
                    </>
                  )}
                </div>
                <div className="ow-card-body">
                  <small>{dateText(o.created_at)}</small>
                  <h2>
                    {p?.name ?? "宠物"}的
                    {o.kind === "model" ? "立体模型" : "纪念肖像"}
                    <ArrowRight size={17} />
                  </h2>
                </div>
              </button>
            );
          })}
        </div>
      )}
      {open && viewing !== null && (
        <AlbumViewer
          selectedId={viewing}
          portraits={portraits}
          pets={data.pets}
          onSelect={setViewing}
          onClose={() => setViewing(null)}
          nav={nav}
        />
      )}
    </Entry>
  );
}
