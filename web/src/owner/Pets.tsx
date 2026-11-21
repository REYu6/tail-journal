import { useRef, useState, type FormEvent } from "react";
import {
  ArrowRight,
  BookHeart,
  Box,
  Camera,
  Download,
  Check,
  Heart,
  ImagePlus,
  Images,
  Pencil,
  Plus,
  Upload,
  X,
} from "lucide-react";
import {
  api,
  dateText,
  errorText,
  modelLink,
  petLink,
  portraitLink,
  same,
  useAction,
  workLabel,
  workLink,
  type Pet,
  type StudioProps,
} from "./data";
import { Blank, Confirm, Entry, Note, SummaryImage } from "./ui";

const species: Record<string, string> = {
  cat: "猫咪",
  dog: "狗狗",
  other: "其他伙伴",
};
export const speciesName = (v: string) => species[v] ?? v;
const occasion: Record<string, string> = {
  life: "为现在的它留档",
  memory: "用老照片做纪念",
};
export async function uploadPhotos(id: string | number, files: File[]) {
  let uploaded = 0;
  for (const file of files) {
    try {
      const body = new FormData();
      body.append("file", file);
      await api("/pets/" + id + "/photos", "POST", body);
      uploaded++;
    } catch (err) {
      throw new Error(
        (uploaded ? "已保存前 " + uploaded + " 张。" : "") +
          file.name +
          " 上传失败：" +
          errorText(err),
      );
    }
  }
}
function checkFiles(files: File[]) {
  if (
    files.some(
      (f) => !["image/jpeg", "image/png", "image/webp"].includes(f.type),
    )
  )
    return "请选择 JPG、PNG 或 WebP 照片。";
  if (files.some((f) => f.size > 10 * 1024 * 1024))
    return "请把每张照片控制在 10 MB 以内。";
  return "";
}
function FilesInput({
  files,
  onChange,
  disabled,
}: {
  files: File[];
  onChange: (v: File[]) => void;
  disabled?: boolean;
}) {
  const [err, setErr] = useState("");
  const input = useRef<HTMLInputElement>(null);
  function add(v: File[]) {
    const note = checkFiles(v);
    setErr(note);
    if (!note) onChange([...files, ...v]);
  }
  return (
    <div className="ow-files">
      <input
        ref={input}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        multiple
        hidden
        disabled={disabled}
        onChange={(e) => {
          add(Array.from(e.target.files ?? []));
          e.target.value = "";
        }}
      />
      <button
        type="button"
        className="ow-drop"
        disabled={disabled}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          if (!disabled) add(Array.from(e.dataTransfer.files));
        }}
        onClick={() => input.current?.click()}
      >
        <Upload size={23} />
        <strong>选取照片，或拖到这里</strong>
        <small>JPG、PNG、WebP · 每张最多 10 MB</small>
      </button>
      {files.length > 0 && (
        <ul className="ow-file-list">
          {files.map((f, i) => (
            <li key={f.name + i}>
              <span>{f.name}</span>
              <button
                aria-label={"移除 " + f.name}
                type="button"
                disabled={disabled}
                onClick={() => onChange(files.filter((_, j) => j !== i))}
              >
                <X size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}
      <Note error={err} />
    </div>
  );
}
export function PetList({ data, nav }: StudioProps) {
  return (
    <Entry
      title="宠物档案"
      intro="记下它的小习惯，也留住每一张珍贵的照片。"
      action={
        <button className="ow-btn" onClick={() => nav("/pets/new")}>
          <Plus size={17} />
          新建档案
        </button>
      }
    >
      {data.pets.length === 0 ? (
        <Blank
          icon={<BookHeart size={33} />}
          title="它的第一份档案"
          text="给它取一个熟悉的称呼，存下照片。等想做纪念品时，这些细节都会在这里。"
          label="为它建档"
          action={() => nav("/pets/new")}
        />
      ) : (
        <div className="ow-cardgrid">
          {data.pets.map((p) => (
            <button
              className="ow-pet-card"
              key={p.id}
              onClick={() => nav(petLink(p))}
            >
              <div className="ow-card-cover">
                <SummaryImage pet={p} />
              </div>
              <div className="ow-card-body">
                <small>
                  {speciesName(p.species)} · {p.photos.length} 张照片
                </small>
                <h2>
                  {p.name}
                  <ArrowRight size={17} />
                </h2>
                <p>{p.traits || p.story || "打开它的档案"}</p>
              </div>
            </button>
          ))}
        </div>
      )}
    </Entry>
  );
}
export function PetForm({ pet, nav, refresh }: StudioProps & { pet?: Pet }) {
  const [name, setName] = useState(pet?.name ?? "");
  const [kind, setKind] = useState(pet?.species ?? "cat");
  const [mode, setMode] = useState(pet?.occasion ?? "life");
  const [traits, setTraits] = useState(pet?.traits ?? "");
  const [story, setStory] = useState(pet?.story ?? "");
  const [files, setFiles] = useState<File[]>([]);
  const createdId = useRef<string | number | null>(pet?.id ?? null);
  const [partiallySaved, setPartiallySaved] = useState(false);
  const action = useAction(refresh);
  async function save(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) {
      action.setError("请输入宠物名字。");
      return;
    }
    await action.run(
      async () => {
        const details = {
          name: name.trim(),
          species: kind,
          occasion: mode,
          traits: traits.trim(),
          story: story.trim(),
        };
        const saved =
          createdId.current != null
            ? await api<Pet>("/pets/" + createdId.current, "PATCH", details)
            : await api<Pet>("/pets", "POST", details);
        createdId.current = saved.id;
        try {
          if (files.length > 0) await uploadPhotos(saved.id, files);
        } catch (err) {
          setPartiallySaved(true);
          setFiles([]);
          await refresh();
          throw err;
        }
        return saved;
      },
      (p) => nav(petLink(p)),
    );
  }
  return (
    <Entry
      title={pet ? "编辑宠物档案" : "为它建一份档案"}
      intro="从名字和照片开始，以后随时可以补充。"
      back={["返回宠物档案", () => nav(pet ? petLink(pet) : "/pets")]}
    >
      <form className="ow-panel ow-form ow-formwide" onSubmit={save}>
        <div className="ow-fieldrow">
          <label>
            宠物名字
            <input
              required
              autoFocus
              maxLength={60}
              placeholder="平时你怎么叫它？"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label>
            伙伴类型
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              {Object.entries(species).map(([v, k]) => (
                <option key={v} value={v}>
                  {k}
                </option>
              ))}
            </select>
          </label>
        </div>
        <fieldset>
          <legend>想怎样记录它</legend>
          <div className="ow-segments">
            {Object.entries(occasion).map(([v, k]) => (
              <label key={v} className={mode === v ? "is-current" : ""}>
                <input
                  type="radio"
                  name="occasion"
                  checked={mode === v}
                  onChange={() => setMode(v)}
                />
                {v === "life" ? <Camera size={17} /> : <Heart size={17} />} {k}
              </label>
            ))}
          </div>
        </fieldset>
        <label>
          它的辨识特征 <small>选填</small>
          <textarea
            value={traits}
            maxLength={1400}
            onChange={(e) => setTraits(e.target.value)}
            rows={2}
            placeholder="比如左耳尖有缺口，只有右前爪是白色。"
          />
        </label>
        <label>
          一段想留住的回忆 <small>选填</small>
          <textarea
            value={story}
            maxLength={4000}
            onChange={(e) => setStory(e.target.value)}
            rows={3}
            placeholder="它有哪些只有你知道的小习惯？"
          />
        </label>
        {!pet && (
          <fieldset>
            <legend>
              原始照片 <small>可以稍后上传</small>
            </legend>
            <p className="ow-field-help">
              {mode === "life"
                ? "正脸、侧身和背部的照片，有助于以后制作立体模型。"
                : "一张看得清脸的老照片就可以开始。"}
            </p>
            <FilesInput
              files={files}
              onChange={setFiles}
              disabled={action.busy}
            />
          </fieldset>
        )}
        <Note error={action.error} />
        <div className="ow-actions">
          <button className="ow-btn" disabled={action.busy}>
            <Check size={17} />
            {action.busy ? "正在保存…" : pet ? "保存修改" : "保存档案"}
          </button>
          {partiallySaved && (
            <button
              type="button"
              className="ow-link"
              onClick={() => nav("/pets/" + createdId.current)}
            >
              查看已保存的档案
            </button>
          )}
        </div>
      </form>
    </Entry>
  );
}
export function PetDetail({
  pet,
  data,
  nav,
  refresh,
}: StudioProps & { pet: Pet }) {
  const [adding, setAdding] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const action = useAction(refresh);
  const works = data.works.filter((w) => same(w.pet_id, pet.id));
  return (
    <Entry
      title={pet.name + "的档案"}
      back={["全部宠物", () => nav("/pets")]}
      action={
        <button
          className="ow-btn ow-secondary"
          onClick={() => nav(petLink(pet) + "/edit")}
        >
          <Pencil size={15} />
          编辑档案
        </button>
      }
    >
      <section className="ow-profile">
        <div className="ow-profile-img">
          <SummaryImage pet={pet} />
        </div>
        <div>
          <small>
            {speciesName(pet.species)} · {pet.photos.length} 张照片
          </small>
          <h2>{pet.name}</h2>
          <p>{pet.traits || "还没有填写辨识特征。"}</p>
          {pet.story && <blockquote>{pet.story}</blockquote>}
          <div className="ow-actions">
            <button className="ow-btn" onClick={() => nav(portraitLink(pet))}>
              <Images size={16} />
              制作肖像
            </button>
            <button
              className="ow-btn ow-secondary"
              onClick={() => nav(modelLink(pet))}
            >
              <Box size={16} />
              制作 3D
            </button>
          </div>
        </div>
      </section>
      <div className="ow-section-head">
        <h2>原始照片</h2>
        <button className="ow-link" onClick={() => setAdding(!adding)}>
          <ImagePlus size={16} />
          {adding ? "收起上传" : "添加照片"}
        </button>
      </div>
      {adding && (
        <div className="ow-panel ow-upload-panel">
          <FilesInput
            files={files}
            onChange={setFiles}
            disabled={action.busy}
          />
          <button
            className="ow-btn"
            disabled={action.busy || !files.length}
            onClick={() =>
              void action.run(
                async () => {
                  try {
                    await uploadPhotos(pet.id, files);
                  } finally {
                    setFiles([]);
                    await refresh();
                  }
                },
                () => setAdding(false),
                "照片已保存。",
              )
            }
          >
            {action.busy ? "正在上传…" : "上传照片"}
          </button>
        </div>
      )}
      <Note error={action.error} notice={action.notice} />
      {pet.photos.length === 0 ? (
        <p className="ow-subtle">
          还没有照片。添加一张原照，就可以开始制作肖像。
        </p>
      ) : (
        <div className="ow-photos">
          {pet.photos.map((p) => (
            <div className="ow-photo" key={p.id}>
              <a
                href={p.url}
                target="_blank"
                rel="noreferrer"
                aria-label={"查看原照 " + p.name}
              >
                <img src={p.url} alt={p.name} loading="lazy" />
              </a>
              <div>
                <span title={p.name}>{p.name}</span>
                {p.original_url && (
                  <a
                    className="ow-original-download"
                    href={p.original_url}
                    download={p.name}
                    aria-label={"下载原照 " + p.name}
                    title="下载原照"
                  >
                    <Download size={15} />
                  </a>
                )}
                <Confirm
                  label="移除"
                  prompt="从档案移除这张照片？"
                  disabled={action.busy}
                  onYes={() =>
                    void action.run(
                      () =>
                        api("/pets/" + pet.id + "/photos/" + p.id, "DELETE"),
                      undefined,
                      "照片已移除。",
                    )
                  }
                />
              </div>
            </div>
          ))}
        </div>
      )}
      {works.length > 0 && (
        <>
          <div className="ow-section-head">
            <h2>肖像制作记录</h2>
          </div>
          <div className="ow-rows">
            {works.map((w) => (
              <button
                key={w.id}
                className="ow-row"
                onClick={() => nav(workLink(w))}
              >
                <span>
                  <strong>
                    {w.title ||
                      data.styles.find((s) => same(s.id, w.style_id))?.name ||
                      "纪念肖像"}
                  </strong>
                  <small>{dateText(w.created_at)}</small>
                </span>
                <span className="ow-row-end">
                  {workLabel(w)}
                  <ArrowRight size={15} />
                </span>
              </button>
            ))}
          </div>
        </>
      )}
      <div className="ow-manage">
        <Confirm
          label="删除这份档案"
          prompt="确认删除？档案内的照片和作品将无法再访问。请先保存需要的文件。"
          disabled={action.busy}
          onYes={() =>
            void action.run(
              () => api("/pets/" + pet.id, "DELETE"),
              () => nav("/pets"),
            )
          }
        />
      </div>
    </Entry>
  );
}
