import { useState, type FormEvent } from "react";
import {
  ArrowRight,
  Box,
  Check,
  CheckCircle2,
  Columns2,
  Scan,
  ImagePlus,
  Layers3,
  Paintbrush,
  ScanEye,
  Sparkles,
} from "lucide-react";
import {
  api,
  money,
  orderLink,
  petLink,
  portraitLink,
  same,
  useAction,
  useRequestKey,
  workLabel,
  workLink,
  type Id,
  type Order,
  type Pet,
  type StudioProps,
  type Work,
} from "./data";
import { Blank, DemoNote, Entry, Note, RefreshButton } from "./ui";
import PhotoCompare from "../PhotoCompare";
import "./proof-motion.css";

export function Create({
  data,
  nav,
  refresh,
  kind,
  search,
}: StudioProps & { kind: "portrait" | "model"; search: URLSearchParams }) {
  const [petId, setPetId] = useState<string>(
    search.get("pet") ?? String(data.pets[0]?.id ?? ""),
  );
  const pet = data.pets.find((p) => same(p.id, petId)) ?? data.pets[0];
  const [chosen, setChosen] = useState<Id[]>(
    pet?.photos.slice(0, kind === "portrait" ? 3 : 1).map((p) => p.id) ?? [],
  );
  const [style, setStyle] = useState<Id>(
    data.styles.find((s) => s.active !== false)?.id ?? "",
  );
  const [source, setSource] = useState<"photos" | "portrait">(
    search.has("candidate") ? "portrait" : "photos",
  );
  const [candidate, setCandidate] = useState<Id>(search.get("candidate") ?? "");
  const [accept, setAccept] = useState(false);
  const action = useAction(refresh);
  const getKey = useRequestKey();
  const model = kind === "model";
  const maxPhotos = model ? 4 : 10;
  const paid = pet
    ? data.orders.filter(
        (o) =>
          same(o.pet_id, pet.id) &&
          o.kind === "portrait" &&
          o.delivery_status === "delivered" &&
          o.payment_status === "paid" &&
          o.candidate_id != null,
      )
    : [];
  const styles = data.styles.filter((s) => s.active !== false);
  function resetPet(p: Pet) {
    setPetId(String(p.id));
    setChosen(p.photos.slice(0, kind === "portrait" ? 3 : 1).map((v) => v.id));
    setCandidate("");
    setSource("photos");
    setAccept(false);
    action.setError("");
  }
  function toggle(id: Id) {
    setChosen((ids) =>
      ids.some((v) => same(v, id))
        ? ids.filter((v) => !same(v, id))
        : [...ids, id],
    );
    setAccept(false);
  }
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!pet) return;
    const sourceIds = source === "photos" ? chosen : [];
    if (source === "photos" && !sourceIds.length) {
      action.setError("请至少选一张原照。");
      return;
    }
    if (model && source === "portrait" && !candidate) {
      action.setError("请先选择一份已交付肖像。");
      return;
    }
    if (!model && !style) {
      action.setError("目前没有可选画风。");
      return;
    }
    if (model) {
      const info = {
        kind,
        pet_id: pet.id,
        ...(source === "portrait"
          ? { candidate_id: candidate }
          : { photo_ids: sourceIds }),
        accept_inference: accept,
      };
      await action.run(
        () =>
          api<Order>("/orders", "POST", { ...info, request_key: getKey(info) }),
        (o) => nav(orderLink(o)),
      );
    } else {
      const info = { pet_id: pet.id, style_id: style, photo_ids: sourceIds };
      await action.run(
        () =>
          api<Work>("/works", "POST", { ...info, request_key: getKey(info) }),
        (w) => nav(workLink(w)),
      );
    }
  }
  return (
    <Entry
      title={model ? "制作 3D 模型" : "制作纪念肖像"}
      intro={
        model
          ? "选好参考照片，留住它从每个角度看过去的模样。"
          : "用熟悉的照片作参考，为它试一幅新的肖像。"
      }
      back={["工作室", () => nav("/")]}
    >
      {!pet ? (
        <Blank
          title="先给这位伙伴建档"
          text="把照片和辨识特征存进档案，就能开始制作。"
          label="新建宠物档案"
          action={() => nav("/pets/new")}
        />
      ) : (
        <div className="ow-create-grid">
          <form className="ow-panel ow-form" onSubmit={submit}>
            <label>
              选择宠物
              <select
                value={String(pet.id)}
                onChange={(e) => {
                  const p = data.pets.find((p) => same(p.id, e.target.value));
                  if (p) resetPet(p);
                }}
              >
                {data.pets.map((p) => (
                  <option value={p.id} key={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
            {model && paid.length > 0 && (
              <fieldset>
                <legend>造型来源</legend>
                <div className="ow-segments">
                  <label className={source === "photos" ? "is-current" : ""}>
                    <input
                      type="radio"
                      name="source"
                      checked={source === "photos"}
                      onChange={() => {
                        setSource("photos");
                        setAccept(false);
                      }}
                    />
                    <ImagePlus size={15} />
                    原照写实款
                  </label>
                  <label className={source === "portrait" ? "is-current" : ""}>
                    <input
                      type="radio"
                      name="source"
                      checked={source === "portrait"}
                      onChange={() => {
                        setSource("portrait");
                        setCandidate(paid[0].candidate_id!);
                        setAccept(false);
                      }}
                    />
                    <Paintbrush size={15} />
                    肖像手办款
                  </label>
                </div>
              </fieldset>
            )}
            {source === "portrait" && model ? (
              <fieldset>
                <legend>选择已交付的肖像</legend>
                <div className="ow-picks">
                  {paid.map((o, i) => {
                    const selected = same(o.candidate_id, candidate);
                    return (
                      <button
                        key={o.id}
                        className={"ow-pick " + (selected ? "is-current" : "")}
                        type="button"
                        aria-pressed={selected}
                        aria-label={"使用第 " + (i + 1) + " 份肖像"}
                        onClick={() => setCandidate(o.candidate_id!)}
                      >
                        <img
                          src={o.downloads[0]?.url || o.preview_url}
                          alt={pet.name + "的定稿 " + (i + 1)}
                        />
                        <span className="ow-check">
                          {selected && <Check size={13} />}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </fieldset>
            ) : (
              <fieldset>
                <legend>选择参考照片</legend>
                <p className="ow-field-help">
                  {model
                    ? "可选 1 至 4 张原照。正脸、侧面和背面都清楚，有助于还原它的体态。"
                    : "可选 1 至 10 张原照。第一张为主参考，其余照片用来核对花纹。"}
                </p>
                {pet.photos.length === 0 ? (
                  <button
                    type="button"
                    className="ow-btn ow-secondary"
                    onClick={() => nav(petLink(pet))}
                  >
                    <ImagePlus size={16} />
                    去档案添加照片
                  </button>
                ) : (
                  <div className="ow-picks">
                    {pet.photos.map((p) => {
                      const i = chosen.findIndex((id) => same(id, p.id));
                      return (
                        <button
                          className={"ow-pick " + (i >= 0 ? "is-current" : "")}
                          type="button"
                          disabled={i < 0 && chosen.length >= maxPhotos}
                          key={p.id}
                          onClick={() => toggle(p.id)}
                          aria-pressed={i >= 0}
                          aria-label={(i >= 0 ? "取消选择" : "选择") + p.name}
                        >
                          <img src={p.url} alt={p.name} />
                          <span className="ow-check">
                            {i >= 0 && <Check size={13} />}
                          </span>
                          {i === 0 && <small>主参考</small>}
                        </button>
                      );
                    })}
                  </div>
                )}
              </fieldset>
            )}
            {!model && (
              <fieldset>
                <legend>选择画风</legend>
                <div className="ow-styles">
                  {styles.map((s) => (
                    <label
                      key={s.id}
                      className={same(s.id, style) ? "is-current" : ""}
                    >
                      <input
                        type="radio"
                        name="style"
                        checked={same(s.id, style)}
                        onChange={() => setStyle(s.id)}
                      />
                      <Paintbrush size={17} />
                      {s.name}
                      {same(s.id, style) && <Check size={14} />}
                    </label>
                  ))}
                </div>
              </fieldset>
            )}
            {model && (source === "portrait" || chosen.length === 1) && (
              <label className="ow-checkbox">
                <input
                  type="checkbox"
                  required
                  checked={accept}
                  onChange={(e) => setAccept(e.target.checked)}
                />
                <span>我了解照片没有拍到的部位会由模型推测补全。</span>
              </label>
            )}
            {pet.traits && (
              <p className="ow-tip">
                <ScanEye size={16} />
                <span>将保留的特征：{pet.traits}</span>
              </p>
            )}
            <DemoNote data={data} kind={model ? "models" : "images"} />
            <Note error={action.error} />
            <button
              className="ow-btn"
              disabled={
                action.busy ||
                (source === "photos" && !chosen.length) ||
                (!model && !styles.length)
              }
            >
              {model ? <Box size={17} /> : <Sparkles size={17} />}{" "}
              {action.busy
                ? "正在提交…"
                : model
                  ? "确认资料，查看订单"
                  : "生成肖像预览"}
            </button>
          </form>
          <aside className="ow-create-aside">
            <img
              className={model ? "ow-corgi-sample" : undefined}
              src={
                model
                  ? "/media/studio-corgi-preview.webp"
                  : "/media/portrait.webp"
              }
              alt={
                model
                  ? "暖橘柯基坐在橡木纹底座上的立体样件"
                  : "宠物肖像作品示例"
              }
            />
            <div>
              <small>作品示例</small>
              <h2>{model ? "立体纪念模型" : "专属纪念肖像"}</h2>
              <p>
                {model
                  ? "付款后开始建模。在线旋转查看，确认外观、通过质检后，领取 GLB 与 STL 文件。"
                  : "先看候选作品，可以提出一次修改。选中满意的版本后，再购买高清无水印原图。"}
              </p>
              <strong>
                {money(model ? data.prices.model : data.prices.portrait)}
                <small> / {model ? "只" : "幅"}</small>
              </strong>
            </div>
          </aside>
        </div>
      )}
    </Entry>
  );
}

const proofSteps = [
  { status: "queued", title: "已入队" },
  { status: "running", title: "制作中" },
  { status: "ready", title: "可选稿" },
] as const;

function ProofProgress({ work }: { work: Work }) {
  const stage = proofSteps.findIndex((step) => step.status === work.status);
  if (stage < 0) return null;

  const current = work.revision_count > 0 ? "修改稿" : "肖像";
  const description = [
    current + "已排队，可以先离开，稍后从宠物档案回来看。",
    "正在制作" + current + "。候选稿完成后会自动出现在这里。",
    current + "已备好，共 " + work.candidates.length + " 份候选稿。",
  ][stage];
  return (
    <section
      className={"proof-progress proof-" + work.status}
      aria-label="肖像制作进度"
    >
      <p role="status" aria-atomic="true">
        {description}
      </p>
      <ol>
        {proofSteps.map((step, index) => (
          <li
            key={step.status}
            data-state={
              index < stage ? "done" : index === stage ? "current" : "next"
            }
            aria-current={index === stage ? "step" : undefined}
          >
            <i aria-hidden="true">
              {(index < stage ||
                (index === stage && step.status === "ready")) && (
                <Check size={10} />
              )}
            </i>
            {step.title}
          </li>
        ))}
      </ol>
    </section>
  );
}

export function WorkDetail({
  data,
  work,
  nav,
  refresh,
}: StudioProps & { work: Work }) {
  const pet = data.pets.find((p) => same(p.id, work.pet_id));
  const style = data.styles.find((s) => same(s.id, work.style_id));
  const [picked, setPicked] = useState<Id | null>(null);
  const [revising, setRevising] = useState(false);
  const [feedback, setFeedback] = useState("");
  const action = useAction(refresh);
  const getKey = useRequestKey();
  const candidates = work.candidates ?? [];
  const selected = candidates.find((c) => same(c.id, picked)) ?? candidates[0];
  const [reference, setReference] = useState<Id | null>(null);
  const [compareMode, setCompareMode] = useState<"slider" | "pair">("slider");
  const refs = work.photo_ids?.length
    ? work.photo_ids.flatMap(
        (id) => pet?.photos.find((p) => same(p.id, id)) ?? [],
      )
    : (pet?.photos ?? []);
  const photo = refs.find((p) => same(p.id, reference)) ?? refs[0];
  const currentNumber = selected ? candidates.indexOf(selected) + 1 : 0;
  const order =
    selected &&
    data.orders.find(
      (o) =>
        o.kind === "portrait" &&
        same(o.candidate_id, selected.id) &&
        ["paid", "unpaid"].includes(o.payment_status) &&
        o.delivery_status !== "cancelled",
    );
  const waiting = ["queued", "running"].includes(work.status);
  const name = pet?.name ?? "宠物";
  function buy() {
    if (!selected) return;
    if (order) {
      nav(orderLink(order));
      return;
    }
    const info = {
      kind: "portrait",
      pet_id: work.pet_id,
      candidate_id: selected.id,
    };
    void action.run(
      () =>
        api<Order>("/orders", "POST", { ...info, request_key: getKey(info) }),
      (o) => nav(orderLink(o)),
    );
  }
  return (
    <Entry
      title={name + "的肖像选稿"}
      intro={style?.name ?? work.title}
      back={["返回宠物档案", () => nav(pet ? petLink(pet) : "/pets")]}
      action={<RefreshButton refresh={refresh} />}
    >
      <DemoNote data={data} kind="images" />
      <ProofProgress work={work} />
      {["failed", "uncertain"].includes(work.status) && (
        <div className="ow-panel">
          <h2>{workLabel(work)}</h2>
          <p>
            {work.error ||
              work.message ||
              "制作没有正常完成，运营人员可以在后台核实。"}
          </p>
        </div>
      )}
      {selected && (
        <>
          <div className="proof-toolbar">
            <div>
              <h2>对照原照</h2>
              <p aria-live="polite" aria-atomic="true">
                正在查看第 {currentNumber} 稿
              </p>
            </div>
            {photo && (
              <div className="proof-modes" role="group" aria-label="对照方式">
                <button
                  type="button"
                  aria-pressed={compareMode === "slider"}
                  onClick={() => setCompareMode("slider")}
                >
                  <Scan size={16} />
                  滑动对照
                </button>
                <button
                  type="button"
                  aria-pressed={compareMode === "pair"}
                  onClick={() => setCompareMode("pair")}
                >
                  <Columns2 size={16} />
                  并排查看
                </button>
              </div>
            )}
          </div>
          {refs.length > 1 && (
            <label className="proof-reference">
              参考照片
              <select
                aria-label="切换参考照片"
                value={photo?.id}
                onChange={(e) => setReference(e.target.value)}
              >
                {refs.map((p, i) => (
                  <option value={p.id} key={p.id}>
                    照片 {i + 1}
                  </option>
                ))}
              </select>
            </label>
          )}
          {photo && compareMode === "slider" ? (
            <PhotoCompare
              className="proof-canvas"
              fit="contain"
              before={{
                src: photo.url,
                alt: name + "的参考原照",
                label: "参考原照",
              }}
              after={{
                src: selected.preview_url,
                alt: name + "的肖像候选稿",
                label: "第 " + currentNumber + " 稿",
              }}
            />
          ) : (
            <div className="ow-comparison proof-pair">
              <figure>
                {photo ? (
                  <img src={photo.url} alt={name + "的参考原照"} />
                ) : (
                  <div className="ow-missing">原照已移除</div>
                )}
                <figcaption>参考原照</figcaption>
              </figure>
              <figure>
                <img
                  key={selected.id}
                  src={selected.preview_url}
                  alt={name + "的肖像候选稿"}
                />
                <figcaption>
                  当前选稿<span>预览</span>
                </figcaption>
              </figure>
            </div>
          )}
          <div className="ow-section-head">
            <h2>选择喜欢的一版</h2>
            <small>{candidates.length} 份候选稿</small>
          </div>
          <div className="ow-candidates proof-choices">
            {candidates.map((c, i) => (
              <button
                key={c.id}
                aria-pressed={same(c.id, selected.id)}
                className={same(c.id, selected.id) ? "is-current" : ""}
                onClick={() => setPicked(c.id)}
              >
                <img src={c.preview_url} alt={"第 " + (i + 1) + " 稿"} />
                <span>
                  {same(c.id, selected.id) ? (
                    <CheckCircle2 size={15} />
                  ) : (
                    <Layers3 size={15} />
                  )}{" "}
                  第 {i + 1} 稿
                </span>
              </button>
            ))}
          </div>
          <div className="ow-actions ow-spaced">
            <button className="ow-btn" disabled={action.busy} onClick={buy}>
              {order
                ? "查看这一版的订单"
                : "选定这版 · " + money(data.prices.portrait)}
              <ArrowRight size={16} />
            </button>
            {work.status === "ready" && work.revision_count < 1 && (
              <button
                className="ow-btn ow-secondary"
                onClick={() => setRevising(!revising)}
              >
                {revising ? "收起修改" : "想调整一点"}
              </button>
            )}
          </div>
        </>
      )}
      {revising && (
        <form
          className="ow-panel ow-form ow-spaced"
          onSubmit={(e) => {
            e.preventDefault();
            if (!feedback.trim()) return;
            void action.run(
              () =>
                api<Work>("/works/" + work.id + "/revise", "POST", {
                  feedback: feedback.trim(),
                }),
              (w) => {
                setRevising(false);
                setFeedback("");
                if (w?.id && !same(w.id, work.id)) nav(workLink(w));
              },
              "修改意见已提交。",
            );
          }}
        >
          <label>
            哪里和它不太一样？
            <textarea
              required
              rows={3}
              value={feedback}
              maxLength={1000}
              onChange={(e) => setFeedback(e.target.value)}
              placeholder="例如鼻子上的黑色斑点应该在右侧。"
            />
          </label>
          <button className="ow-btn" disabled={action.busy || !feedback.trim()}>
            提交这次修改
          </button>
        </form>
      )}
      <Note error={action.error} notice={action.notice} />
      {pet && !selected && !waiting && (
        <button
          className="ow-btn ow-secondary ow-spaced"
          onClick={() => nav(portraitLink(pet))}
        >
          返回制作页面
        </button>
      )}
    </Entry>
  );
}
