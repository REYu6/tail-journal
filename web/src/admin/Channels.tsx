import { useRef, useState } from "react";
import { QRCodeCanvas } from "qrcode.react";
import { Download, ExternalLink, QrCode } from "lucide-react";
import { money } from "../common";
import {
  ActionDialog,
  Blank,
  Field,
  type Action,
  type Row,
  type Run,
} from "./shared";
export default function Channels({
  rows,
  admin,
  query,
  run,
}: {
  rows: Row[];
  admin: boolean;
  query: string;
  run: Run;
}) {
  const [edit, setEdit] = useState<Row | null>(null),
    [qr, setQr] = useState(""),
    [working, setWorking] = useState(false);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [action, setAction] = useState<Action | null>(null);
  const editField = (key: string, value: string) =>
    setEdit((s) => ({ ...s, [key]: value }));
  const create = () =>
    setEdit({
      id: "",
      name: "",
      code: "",
      commission: 0,
      acquisition_cost: 0,
      labor_cost: 0,
    });
  const matching = rows.filter((r) =>
    [r.name, r.code].some((v) =>
      (v || "").toLowerCase().includes(query.toLowerCase()),
    ),
  );
  return (
    <>
      {admin && (
        <button className="adm-primary" onClick={create}>
          新建合作渠道
        </button>
      )}
      {edit && (
        <form
          className="adm-channel-form"
          onSubmit={async (e) => {
            e.preventDefault();
            setWorking(true);
            const payload: Row = {
              name: edit.name,
              commission: Math.round(edit.commission * 100),
              acquisition_cost: Math.round(edit.acquisition_cost * 100),
              labor_cost: Math.round(edit.labor_cost * 100),
            };
            if (!edit.id) payload.code = edit.code;
            try {
              if (
                await run(
                  "/admin/channels" + (edit.id ? "/" + edit.id : ""),
                  payload,
                  edit.id ? "PATCH" : "POST",
                )
              )
                setEdit(null);
            } finally {
              setWorking(false);
            }
          }}
        >
          <h3>{edit.id ? "更新渠道费用" : "添加门店"}</h3>
          <div className="adm-form-grid">
            <Field title="门店名称">
              <input
                maxLength={80}
                required
                value={edit.name}
                onChange={(e) => editField("name", e.target.value)}
              />
            </Field>
            <Field title="推广码（2 至 40 位）">
              <input
                disabled={!!edit.id}
                required
                minLength={2}
                maxLength={40}
                pattern="[a-zA-Z0-9_\-]{2,40}"
                value={edit.code}
                onChange={(e) => editField("code", e.target.value)}
              />
            </Field>
            {(
              [
                ["commission", "每笔交付佣金"],
                ["acquisition_cost", "累计获客支出"],
                ["labor_cost", "累计人工支出"],
              ] as const
            ).map(([k, title]) => (
              <Field key={k} title={title + "（元）"}>
                <input
                  required
                  min="0"
                  step=".01"
                  type="number"
                  value={edit[k]}
                  onChange={(e) => editField(k, e.target.value)}
                />
              </Field>
            ))}
          </div>
          <div className="adm-actions">
            <button type="button" onClick={() => setEdit(null)}>
              取消
            </button>
            <button disabled={working} className="adm-primary">
              保存渠道
            </button>
          </div>
        </form>
      )}
      {!matching.length && <Blank>没有符合条件的渠道</Blank>}
      {matching.map((c) => (
        <article className="adm-record adm-pad" key={c.id}>
          <header>
            <strong>{c.name}</strong>
            <b>预估贡献 ¥{money(c.estimated_contribution || 0)}</b>
          </header>
          <p>
            有预览的主人 {c.preview_users} 位　已付款 {c.paid_orders} 单　退款{" "}
            {c.refund_orders} 单　演示订单 {c.demo_orders} 单
          </p>
          <p>
            实收 ¥{money(c.revenue)}　预估调用 ¥{money(c.estimated_model_cost)}
            　应计佣金 ¥{money(c.commission_accrued ?? c.commission_due)}
            　已登记结算 ¥{money(c.commission_settled || 0)}　待结 ¥
            {money(c.commission_due)}　获客 ¥{money(c.acquisition_cost)}　人工 ¥
            {money(c.labor_cost)}
          </p>
          {c.id !== "direct" && (
            <>
              <p>
                推广入口　
                <a
                  className="adm-link"
                  href={c.link}
                  target="_blank"
                  rel="noreferrer"
                >
                  {location.origin + c.link}
                  <ExternalLink size={13} />
                </a>
              </p>
              <div className="adm-actions">
                <button onClick={() => setQr(qr === c.id ? "" : c.id)}>
                  <QrCode size={15} />
                  {qr === c.id ? "收起二维码" : "推广二维码"}
                </button>
                {admin && c.commission_due > 0 && (
                  <button
                    onClick={() =>
                      setAction({
                        title: "登记已结算",
                        field: "转账凭证编号或备注",
                        detail:
                          "登记已完成的门店佣金转账，共 ¥" +
                          money(c.commission_due) +
                          "。",
                        submit: (note) =>
                          run("/admin/channels/" + c.id + "/settle", { note }),
                      })
                    }
                  >
                    登记已结算
                  </button>
                )}
                {admin && (
                  <button
                    onClick={() =>
                      setEdit({
                        ...c,
                        commission: c.commission / 100,
                        acquisition_cost: c.acquisition_cost / 100,
                        labor_cost: c.labor_cost / 100,
                      })
                    }
                  >
                    编辑渠道
                  </button>
                )}
              </div>
              {qr === c.id && (
                <div className="adm-qr">
                  <QRCodeCanvas
                    ref={canvas}
                    value={location.origin + c.link}
                    size={168}
                    marginSize={3}
                    title={c.name + "推广二维码"}
                  />
                  <button
                    onClick={() => {
                      if (!canvas.current) return;
                      const a = document.createElement("a");
                      a.href = canvas.current.toDataURL("image/png");
                      a.download = c.code + "-二维码.png";
                      a.click();
                    }}
                  >
                    <Download size={15} />
                    下载二维码
                  </button>
                </div>
              )}
            </>
          )}
        </article>
      ))}
      {action && (
        <ActionDialog action={action} onClose={() => setAction(null)} />
      )}
    </>
  );
}
