import { useState } from "react";
import { Plus } from "lucide-react";
import { Field, Tag, type Row, type Run } from "./shared";
export default function Settings({
  data,
  run,
  userId,
  refresh,
}: {
  data: Row;
  run: Run;
  userId: string;
  refresh: () => Promise<void>;
}) {
  const [prices, setPrices] = useState({
    portrait: String(data.prices.portrait / 100),
    model: String(data.prices.model / 100),
  });
  const [limit, setLimit] = useState(data.daily_limit);
  const [styles, setStyles] = useState<Row[]>(
    data.styles.map((s: Row) => ({ ...s })),
  );
  const [busy, setBusy] = useState(false);
  const [rates, setRates] = useState<Row>({ ...data.unit_costs });
  const testPets = data.pets.filter(
    (p: Row) => p.user_id === userId && p.photos.length,
  );
  const [testPet, setTestPet] = useState(String(testPets[0]?.id || ""));
  const [testStyle, setTestStyle] = useState(String(styles[0]?.id || ""));
  const pet = testPets.find((p: Row) => p.id === testPet),
    draft = styles.find((s) => s.id === testStyle);
  const previews = data.works
    .filter((w: Row) => w.user_id === userId && w.style_id === "draft")
    .slice(0, 3);
  async function test() {
    if (!pet || !draft || !draft.name.trim() || !draft.prompt.trim()) return;
    setBusy(true);
    try {
      await run("/admin/styles/preview", {
        pet_id: pet.id,
        photo_ids: [pet.photos[0].id],
        name: draft.name,
        prompt: draft.prompt,
      });
    } finally {
      setBusy(false);
    }
  }
  function edit(i: number, key: string, val: any) {
    setStyles((ss) => ss.map((s, ix) => (ix === i ? { ...s, [key]: val } : s)));
  }
  return (
    <form
      className="adm-panel adm-settings"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        try {
          await run(
            "/admin/settings",
            {
              prices: {
                portrait: Math.round(+prices.portrait * 100),
                model: Math.round(+prices.model * 100),
              },
              daily_limit: +limit,
              unit_costs: {
                portrait_image_cny: Number(rates.portrait_image_cny),
                model_usd: Number(rates.model_usd),
                usd_cny: Number(rates.usd_cny),
              },
              styles: styles.map(({ id, name, prompt, active }) => ({
                id,
                name,
                prompt,
                active,
              })),
            },
            "PATCH",
          );
        } finally {
          setBusy(false);
        }
      }}
    >
      <h3>商品与额度</h3>
      <div className="adm-form-grid">
        {(["portrait", "model"] as const).map((k) => (
          <Field
            key={k}
            title={(k === "portrait" ? "纪念肖像" : "3D 模型") + "单价（元）"}
          >
            <input
              type="number"
              min=".01"
              max="10000"
              step=".01"
              required
              value={prices[k]}
              onChange={(e) => setPrices({ ...prices, [k]: e.target.value })}
            />
          </Field>
        ))}
        <Field title="每人每日肖像任务数">
          <input
            type="number"
            min="1"
            max="100"
            required
            value={limit}
            onChange={(e) => setLimit(e.target.value)}
          />
        </Field>
      </div>
      <h3>预估调用成本</h3>
      <div className="adm-form-grid">
        {[
          ["portrait_image_cny", "生图单张（元）"],
          ["model_usd", "建模单次（美元）"],
          ["usd_cny", "美元兑人民币预算汇率"],
        ].map(([k, label]) => (
          <Field key={k} title={label}>
            <input
              type="number"
              required
              min={k === "usd_cny" ? ".001" : "0"}
              step=".001"
              value={rates[k]}
              onChange={(e) => setRates({ ...rates, [k]: e.target.value })}
            />
          </Field>
        ))}
      </div>
      <header>
        <h3>画风模板</h3>
        <button
          type="button"
          onClick={() =>
            setStyles((ss) => [
              ...ss,
              {
                id: "style_" + crypto.randomUUID().slice(0, 8),
                name: "",
                prompt: "",
                active: false,
              },
            ])
          }
        >
          <Plus size={15} />
          添加画风
        </button>
      </header>
      {styles.map((s, i) => (
        <div className="adm-style" key={s.id}>
          <Field title="画风名称">
            <input
              required
              maxLength={40}
              value={s.name}
              onChange={(e) => edit(i, "name", e.target.value)}
            />
          </Field>
          <label className="adm-checkbox">
            <input
              type="checkbox"
              checked={s.active}
              onChange={(e) => edit(i, "active", e.target.checked)}
            />
            用户可选
          </label>
          <Field title="风格提示词">
            <textarea
              required
              maxLength={1400}
              rows={2}
              value={s.prompt}
              onChange={(e) => edit(i, "prompt", e.target.value)}
            />
          </Field>
        </div>
      ))}
      <div className="adm-style-test">
        <h3>试样预览</h3>
        <p>使用管理账号自己档案中的照片测试草稿。真实模型会产生调用费用。</p>
        {testPets.length ? (
          <div className="adm-form-grid">
            <Field title="试样宠物">
              <select
                value={testPet}
                onChange={(e) => setTestPet(e.target.value)}
              >
                {testPets.map((p: Row) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field title="试样画风">
              <select
                value={testStyle}
                onChange={(e) => setTestStyle(e.target.value)}
              >
                {styles.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name || "未命名画风"}
                  </option>
                ))}
              </select>
            </Field>
          </div>
        ) : (
          <a className="adm-link" href="/pets/new">
            为测试宠物建档并上传照片
          </a>
        )}
        <div className="adm-actions">
          <button
            type="button"
            onClick={() => void test()}
            disabled={
              busy || !pet || !draft?.prompt?.trim() || !draft?.name?.trim()
            }
          >
            生成一个试样
          </button>
          <button type="button" onClick={() => void refresh()}>
            刷新试样结果
          </button>
        </div>
        {previews.map((w: Row) => (
          <div className="adm-photos" key={w.id}>
            <small>{w.title}　</small>
            <Tag value={w.status} />
            {w.candidates.map((c: Row) => (
              <a
                href={c.preview_url}
                key={c.id}
                target="_blank"
                rel="noreferrer"
              >
                <img alt="画风草稿试样" src={c.preview_url} />
              </a>
            ))}
          </div>
        ))}
      </div>
      <button className="adm-primary" disabled={busy}>
        {busy ? "正在保存…" : "发布设置"}
      </button>
    </form>
  );
}
