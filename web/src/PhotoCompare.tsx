import { useState, type CSSProperties } from "react";
import { ChevronsLeftRight } from "lucide-react";
import "./PhotoCompare.css";

type CompareImage = { src: string; alt: string; label?: string };

export type PhotoCompareProps = {
  before: CompareImage;
  after: CompareImage;
  className?: string;
  fit?: "cover" | "contain";
  position?: string;
  initial?: number;
  label?: string;
};

export default function PhotoCompare({
  before,
  after,
  className = "",
  fit = "cover",
  position = "center",
  initial = 50,
  label = "拖动比较原照与作品",
}: PhotoCompareProps) {
  const [split, setSplit] = useState(() =>
    Math.max(0, Math.min(100, Math.round(initial))),
  );
  const viewStyle = {
    "--compare-split": split + "%",
    "--compare-fit": fit,
    "--compare-position": position,
  } as CSSProperties;
  const beforeLabel = before.label ?? "原照";
  const afterLabel = after.label ?? "作品";

  return (
    <div className={"photo-compare " + className} style={viewStyle}>
      <div className="photo-compare-frame photo-compare-after">
        <img key={after.src} src={after.src} alt={after.alt} draggable={false} />
        <span aria-hidden="true">{afterLabel}</span>
      </div>
      <div className="photo-compare-frame photo-compare-before">
        <img src={before.src} alt={before.alt} draggable={false} />
        <span aria-hidden="true">{beforeLabel}</span>
      </div>
      <input
        type="range"
        className="photo-compare-range"
        min="0"
        max="100"
        step="1"
        value={split}
        onChange={(event) => setSplit(event.currentTarget.valueAsNumber)}
        aria-label={label}
        aria-valuetext={
          beforeLabel +
          " " +
          split +
          "%，" +
          afterLabel +
          " " +
          (100 - split) +
          "%"
        }
      />
      <div className="photo-compare-rule" aria-hidden="true" />
      <div className="photo-compare-knob" aria-hidden="true">
        <ChevronsLeftRight size={20} strokeWidth={1.8} />
      </div>
    </div>
  );
}
