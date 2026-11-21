import { useState } from "react";
import { Activity, Box, Gauge } from "lucide-react";
import { money } from "../common";
import type { Row } from "./shared";
function dayKey(date: Date) {
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0"),
  ].join("-");
}
export default function Usage({ data }: { data: Row }) {
  const today = dayKey(new Date());
  const [from, setFrom] = useState(today),
    [to, setTo] = useState(today);
  const rows = (data.jobs as Row[]).filter((j) => {
    const d = dayKey(new Date(j.created_at));
    return (!from || d >= from) && (!to || d <= to);
  });
  const portraits = rows.filter((j) => j.kind === "portrait"),
    models = rows.filter((j) => j.kind === "model");
  const rates = data.unit_costs || {};
  const cost = rows.reduce(
    (sum, j) =>
      j.provider_mode === "live" && j.external_id
        ? sum +
          Number(j.request_count || 1) *
            (j.kind === "portrait"
              ? rates.portrait_image_cny
              : rates.model_usd * rates.usd_cny)
        : sum,
    0,
  );
  return (
    <section className="adm-panel">
      <header>
        <h3>制作与用量</h3>
      </header>
      <div className="adm-range">
        <label>
          起始日期{" "}
          <input
            type="date"
            value={from}
            max={to || undefined}
            onChange={(e) => setFrom(e.target.value)}
          />
        </label>
        <label>
          结束日期{" "}
          <input
            type="date"
            value={to}
            min={from || undefined}
            onChange={(e) => setTo(e.target.value)}
          />
        </label>
        <button
          onClick={() => {
            setFrom("");
            setTo("");
          }}
        >
          全部日期
        </button>
      </div>
      <div className="adm-facts">
        <span>
          <Activity />
          肖像任务 <b>{portraits.length}</b>
        </span>
        <span>
          <Box />
          3D 任务 <b>{models.length}</b>
        </span>
        <span>
          <Gauge />
          预估调用费用 <b>¥{money(Math.round(cost * 100))}</b>
        </span>
      </div>
      <p className="adm-caption">
        按任务创建日期统计。费用使用已获供应商任务号的真实请求和工作室设定的预算单价。
      </p>
    </section>
  );
}
