import { useEffect, useRef, useState, type TouchEvent } from "react";
import {
  ArrowRight,
  ChevronLeft,
  ChevronRight,
  Download,
  Images,
  X,
} from "lucide-react";
import {
  dateText,
  orderLink,
  same,
  type Id,
  type Nav,
  type Order,
  type Pet,
} from "./data";
import "./album-motion.css";

export function AlbumViewer({
  portraits,
  selectedId,
  pets,
  onSelect,
  onClose,
  nav,
}: {
  portraits: Order[];
  selectedId: Id;
  pets: Pet[];
  onSelect: (id: Id) => void;
  onClose: () => void;
  nav: Nav;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const start = useRef<{ x: number; y: number } | null>(null);
  const [direction, setDirection] = useState<"forward" | "back">("forward");
  const index = portraits.findIndex((o) => same(o.id, selectedId));
  const order = portraits[index];
  const pet = pets.find((p) => same(p.id, order?.pet_id));
  const file = order?.downloads[0];
  const multiple = portraits.length > 1;

  useEffect(() => {
    const node = dialog.current;
    if (!node) return;
    const trigger = document.activeElement;
    node.showModal();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      node.close();
      document.body.style.overflow = previousOverflow;
      if (trigger instanceof HTMLElement && trigger.isConnected)
        trigger.focus({ preventScroll: true });
    };
  }, []);

  function flip(delta: number) {
    if (!multiple || index < 0) return;
    setDirection(delta > 0 ? "forward" : "back");
    onSelect(
      portraits[(index + delta + portraits.length) % portraits.length].id,
    );
  }

  function finishSwipe(e: TouchEvent<HTMLElement>) {
    const beginning = start.current;
    start.current = null;
    if (!beginning || e.touches.length || !e.changedTouches.length) return;
    const touch = e.changedTouches[0];
    const dx = touch.clientX - beginning.x;
    const dy = touch.clientY - beginning.y;
    if (Math.abs(dx) >= 48 && Math.abs(dx) > Math.abs(dy) * 1.6)
      flip(dx < 0 ? 1 : -1);
  }
  if (!order) return null;
  return (
    <dialog
      className="ow-album-lightbox"
      ref={dialog}
      aria-labelledby="album-viewer-title"
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      onKeyDown={(e) => {
        if (e.altKey || e.ctrlKey || e.metaKey || !multiple) return;
        if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
          e.preventDefault();
          flip(e.key === "ArrowRight" ? 1 : -1);
        }
      }}
    >
      <div className="ow-album-paper">
        <header className="ow-viewer-heading">
          <div>
            <Images size={17} />
            <span>纪念相册</span>
          </div>
          <button
            type="button"
            className="ow-viewer-icon"
            aria-label="关闭作品预览"
            onClick={onClose}
            autoFocus
          >
            <X size={20} />
          </button>
        </header>
        <figure className="ow-viewer-figure">
          <div
            className="ow-viewer-stage"
            onTouchStart={(e) => {
              const t = e.touches[0];
              start.current =
                e.touches.length === 1 ? { x: t.clientX, y: t.clientY } : null;
            }}
            onTouchMove={(e) => {
              if (e.touches.length !== 1) start.current = null;
            }}
            onTouchCancel={() => {
              start.current = null;
            }}
            onTouchEnd={finishSwipe}
          >
            <img
              key={order.id}
              className={"ow-viewer-art ow-viewer-" + direction}
              src={file?.url ?? order.preview_url}
              alt={(pet?.name ?? "宠物") + "的纪念肖像"}
              draggable={false}
            />
          </div>
          <figcaption>
            <div
              className="ow-viewer-caption"
              aria-live="polite"
              aria-atomic="true"
            >
              <small>{dateText(order.created_at)}</small>
              <h2 id="album-viewer-title">{pet?.name ?? "宠物"}的纪念肖像</h2>
              <span className="ow-slide-position">
                {index + 1} / {portraits.length}
              </span>
            </div>
            {multiple && (
              <div className="ow-viewer-controls">
                <button
                  type="button"
                  className="ow-viewer-icon"
                  aria-label="上一幅肖像"
                  onClick={() => flip(-1)}
                >
                  <ChevronLeft size={21} />
                </button>
                <button
                  type="button"
                  className="ow-viewer-icon"
                  aria-label="下一幅肖像"
                  onClick={() => flip(1)}
                >
                  <ChevronRight size={21} />
                </button>
              </div>
            )}
          </figcaption>
        </figure>
        <div className="ow-viewer-foot">
          {file && (
            <a className="ow-btn" href={file.url} download={file.name}>
              <Download size={16} />
              下载高清肖像
            </a>
          )}
          <button
            type="button"
            className="ow-link"
            onClick={() => {
              onClose();
              nav(orderLink(order));
            }}
          >
            订单详情 <ArrowRight size={15} />
          </button>
        </div>
      </div>
    </dialog>
  );
}

export function AlbumReceipt({
  delivered,
  nav,
}: {
  delivered: boolean;
  nav: Nav;
}) {
  const previous = useRef(delivered);
  const [arrived, setArrived] = useState(false);
  useEffect(() => {
    setArrived(delivered && !previous.current);
    previous.current = delivered;
  }, [delivered]);
  if (!delivered) return null;
  return (
    <div
      className={"ow-album-receipt" + (arrived ? " just-delivered" : "")}
      onAnimationEnd={() => setArrived(false)}
    >
      <span className="ow-receipt-icon">
        <Images size={19} />
      </span>
      <strong role="status">已收进纪念相册</strong>
      <button type="button" className="ow-link" onClick={() => nav("/album")}>
        查看纪念相册 <ArrowRight size={14} />
      </button>
    </div>
  );
}
