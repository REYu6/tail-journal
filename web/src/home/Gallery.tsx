import { useEffect, useRef, useState, type CSSProperties } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  ChevronLeft,
  ChevronRight,
  X,
} from "lucide-react";
import "./Gallery.css";

const examples = [
  {
    id: "momo",
    title: "墨墨的白手套",
    type: "portrait",
    style: "纸本铅绘",
    image: "tuxedo",
    alt: "白爪黑猫的纸本铅绘肖像",
    detail: "层层叠叠的细线勾出浅色胡须，也记下它特别的白色前爪。",
  },
  {
    id: "coco",
    title: "可可的卷卷毛",
    type: "model",
    style: "黏土手办",
    image: "poodle",
    alt: "一只棕色贵宾犬的黏土手办效果图",
    detail: "用柔和的黏土块面保留它的小卷毛和微微歪头的姿态。",
  },
  {
    id: "mountain",
    title: "小山的眼神",
    type: "portrait",
    style: "复古油画",
    image: "collie",
    alt: "鼠尾草绿色背景的边境牧羊犬油画肖像",
    detail: "深浅不同的笔触，勾出了鼻尖的白线和那双熟悉的眼睛。",
  },
] as const;

const filters = [
  ["all", "全部"],
  ["portrait", "纪念肖像"],
  ["model", "3D 模型"],
] as const;

type Filter = (typeof filters)[number][0];
type Example = (typeof examples)[number];

function Exhibition({
  items,
  start,
  onClose,
  onMake,
}: {
  items: readonly Example[];
  start: number;
  onClose: () => void;
  onMake: (item: Example) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const swipe = useRef<{ id: number; x: number; y: number } | null>(null);
  const [index, setIndex] = useState(start);
  const [direction, setDirection] = useState(0);
  const item = items[index];
  const canBrowse = items.length > 1;

  useEffect(() => {
    const node = dialog.current;
    node?.showModal();
    return () => node?.close();
  }, []);

  function turn(by: -1 | 1) {
    if (!canBrowse) return;
    setDirection(by);
    setIndex((current) => (current + by + items.length) % items.length);
  }

  return (
    <dialog
      ref={dialog}
      className="showcase exhibit-dialog"
      aria-labelledby="exhibit-title"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      onKeyDown={(event) => {
        if (!canBrowse || event.altKey || event.ctrlKey || event.metaKey)
          return;
        if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
          event.preventDefault();
          turn(event.key === "ArrowLeft" ? -1 : 1);
        }
      }}
    >
      <div className="exhibit-layout">
        <button
          type="button"
          autoFocus
          className="showcase-close exhibit-close"
          onClick={onClose}
          aria-label="关闭预览"
        >
          <X size={19} />
        </button>
        <div
          className="exhibit-mat"
          onPointerDown={(event) => {
            if (event.pointerType !== "touch" || !canBrowse) return;
            if (!event.isPrimary) {
              swipe.current = null;
              return;
            }
            swipe.current = {
              id: event.pointerId,
              x: event.clientX,
              y: event.clientY,
            };
            event.currentTarget.setPointerCapture(event.pointerId);
          }}
          onPointerCancel={() => {
            swipe.current = null;
          }}
          onPointerUp={(event) => {
            const start = swipe.current;
            swipe.current = null;
            if (!start || start.id !== event.pointerId) return;
            const dx = event.clientX - start.x;
            const dy = event.clientY - start.y;
            if (Math.abs(dx) >= 46 && Math.abs(dx) > Math.abs(dy) * 1.4)
              turn(dx < 0 ? 1 : -1);
          }}
        >
          <img
            key={item.id}
            className={direction < 0 ? "exhibit-back" : "exhibit-forward"}
            src={"/media/" + item.image + ".webp"}
            alt={item.alt}
            draggable={false}
          />
        </div>
        <div className="exhibit-info">
          <div key={item.id} className="exhibit-description">
            <p className="exhibit-style">{item.style} · 风格示例</p>
            <h2 id="exhibit-title">{item.title}</h2>
            <p>{item.detail}</p>
          </div>
          <button
            className="btn forest"
            type="button"
            onClick={() => onMake(item)}
          >
            为我的宠物制作 <ArrowRight size={16} />
          </button>
          {canBrowse && (
            <div className="exhibit-browse">
              <button
                type="button"
                onClick={() => turn(-1)}
                aria-label="上一件作品"
              >
                <ChevronLeft size={18} />
              </button>
              <span role="status" aria-atomic="true" aria-live="polite">
                <span aria-hidden="true">
                  {index + 1} / {items.length}
                </span>
                <span className="exhibit-reader">
                  第 {index + 1} 件，共 {items.length} 件，{item.title}
                </span>
              </span>
              <button
                type="button"
                onClick={() => turn(1)}
                aria-label="下一件作品"
              >
                <ChevronRight size={18} />
              </button>
            </div>
          )}
        </div>
      </div>
    </dialog>
  );
}

export default function Gallery({
  navigate,
}: {
  navigate: (path: string) => void;
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const [selected, setSelected] = useState<number | null>(null);
  const trigger = useRef<HTMLButtonElement | null>(null);
  const visible = examples.filter(
    (item) => filter === "all" || item.type === filter,
  );

  function closePreview() {
    setSelected(null);
    // React removes the modal on commit. Restore the exact card, even after browsing.
    requestAnimationFrame(() =>
      trigger.current?.focus({ preventScroll: true }),
    );
  }

  return (
    <section
      className="gallery exhibit-gallery"
      id="gallery"
      aria-labelledby="gallery-title"
    >
      <div className="section-head">
        <div>
          <h2 id="gallery-title">作品小展</h2>
          <p>看看不同画风与材质里的小小主角。</p>
        </div>
        <div
          className="gallery-filters exhibit-filters"
          role="group"
          aria-label="作品类型"
          style={
            {
              "--exhibit-filter": filters.findIndex(
                ([value]) => filter === value,
              ),
            } as CSSProperties
          }
        >
          {filters.map(([value, text]) => (
            <button
              type="button"
              aria-pressed={filter === value}
              onClick={() => setFilter(value)}
              key={value}
            >
              {text}
            </button>
          ))}
        </div>
      </div>
      <span
        className="exhibit-reader"
        role="status"
        aria-live="polite"
        aria-atomic="true"
      >
        当前展示 {visible.length} 件作品
      </span>
      <div className="gallery-grid" key={filter}>
        {visible.map((item, index) => (
          <button
            type="button"
            key={item.id}
            className="gallery-tile"
            aria-label={"预览" + item.title + "，" + item.style}
            aria-haspopup="dialog"
            onClick={(event) => {
              trigger.current = event.currentTarget;
              setSelected(index);
            }}
          >
            <div>
              <img
                loading="lazy"
                src={"/media/" + item.image + ".webp"}
                alt={item.alt}
              />
              <span>
                <ArrowUpRight size={18} />
              </span>
            </div>
            <span className="exhibit-caption">
              <strong>{item.title}</strong>
              <small>{item.style}</small>
            </span>
          </button>
        ))}
      </div>
      {selected !== null && (
        <Exhibition
          items={visible}
          start={selected}
          onClose={closePreview}
          onMake={(item) => {
            setSelected(null);
            navigate("/create/" + item.type);
          }}
        />
      )}
    </section>
  );
}
