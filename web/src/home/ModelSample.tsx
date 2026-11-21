import { useEffect, useRef, useState } from "react";
import type { ModelViewerElement } from "@google/model-viewer";
import {
  ArrowRight,
  MoveHorizontal,
  Minus,
  Pause,
  Play,
  Plus,
  RotateCcw,
  X,
} from "lucide-react";
import "./ModelSample.css";

const frontOrbit = "-26deg 78deg 105%";
const sampleTitle = "暖橘柯基";
const materialDetail = "陶偶质感 · 橡木纹底座";

export default function ModelSample({
  onClose,
  onMake,
}: {
  onClose: () => void;
  onMake: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const stage = useRef<HTMLDivElement>(null);
  const model = useRef<ModelViewerElement | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [status, setStatus] = useState<"loading" | "ready" | "failed">(
    "loading",
  );
  const [rotating, setRotating] = useState(false);
  const [reduced, setReduced] = useState(
    () => matchMedia("(prefers-reduced-motion: reduce)").matches,
  );

  useEffect(() => {
    const node = dialog.current!;
    const trigger = document.activeElement;
    const formerOverflow = document.body.style.overflow;
    node.showModal();
    document.body.style.overflow = "hidden";
    return () => {
      node.close();
      document.body.style.overflow = formerOverflow;
      if (trigger instanceof HTMLElement && trigger.isConnected)
        trigger.focus({ preventScroll: true });
    };
  }, []);

  useEffect(() => {
    const preference = matchMedia("(prefers-reduced-motion: reduce)");
    const sync = () => {
      setReduced(preference.matches);
      if (preference.matches) setRotating(false);
    };
    preference.addEventListener("change", sync);
    return () => preference.removeEventListener("change", sync);
  }, []);

  useEffect(() => {
    let active = true;
    let element: ModelViewerElement | undefined;
    const loaded = () => {
      if (active) setStatus("ready");
    };
    const failed = () => {
      if (active) {
        setStatus("failed");
        setRotating(false);
      }
    };
    setStatus("loading");
    setRotating(false);
    void import("@google/model-viewer")
      .then(() => {
        if (!active || !stage.current) return;
        element = document.createElement("model-viewer") as ModelViewerElement;
        element.addEventListener("load", loaded);
        element.addEventListener("error", failed);
        element.alt = "一只坐在圆木底座上的奶油色柯基陶偶";
        element.environmentImage = "/media/studio-light.hdr";
        element.setAttribute("tone-mapping", "neutral");
        element.exposure = 0.88;
        element.shadowIntensity = 0.8;
        element.shadowSoftness = 0.8;
        element.cameraControls = true;
        element.disablePan = true;
        element.cameraOrbit = frontOrbit;
        element.cameraTarget = "auto 90% auto";
        element.setAttribute("rotation-per-second", "12deg");
        element.autoRotateDelay = 0;
        element.setAttribute("interaction-prompt", "none");
        element.setAttribute("touch-action", "pan-y");
        element.setAttribute("loading", "eager");
        element.setAttribute(
          "interpolation-decay",
          matchMedia("(prefers-reduced-motion: reduce)").matches ? "0" : "50",
        );
        model.current = element;
        stage.current.appendChild(element);
        // The viewer caches rejected GLB loads; a deliberate retry needs a new cache key.
        element.src =
          "/media/studio-corgi.glb" + (attempt ? "?retry=" + attempt : "");
      })
      .catch(failed);
    return () => {
      active = false;
      element?.removeEventListener("load", loaded);
      element?.removeEventListener("error", failed);
      element?.remove();
      model.current = null;
    };
  }, [attempt]);

  useEffect(() => {
    if (!model.current) return;
    model.current.autoRotate = rotating && !reduced && status === "ready";
    model.current.setAttribute("interpolation-decay", reduced ? "0" : "50");
  }, [rotating, reduced, status]);
  function reset() {
    const element = model.current;
    if (!element) return;
    setRotating(false);
    element.autoRotate = false;
    element.resetTurntableRotation();
    element.cameraOrbit = frontOrbit;
    element.fieldOfView = "auto";
    element.jumpCameraToGoal();
  }

  return (
    <dialog
      className="ms-modal"
      ref={dialog}
      aria-labelledby="sample-model-title"
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="ms-panel">
        <header className="ms-header">
          <div className="ms-heading">
            <h2 id="sample-model-title">{sampleTitle}</h2>
            <p>{materialDetail}</p>
          </div>
          <button
            type="button"
            className="ms-icon"
            onClick={onClose}
            autoFocus
            aria-label="关闭 3D 样件"
          >
            <X size={20} />
          </button>
        </header>
        <div className="ms-view">
          <div
            className="ms-stage"
            ref={stage}
            style={{ visibility: status === "failed" ? "hidden" : "visible" }}
          />
          {status !== "ready" && (
            <div className="ms-fallback">
              <img
                src="/media/studio-corgi-preview.webp"
                alt="暖橘柯基陶偶与木纹底座的展示图"
              />
              <div role="status">
                {status === "failed"
                  ? "立体视图暂未载入，你可以先查看样件展示图。"
                  : "正在打开立体样件…"}
                {status === "failed" && (
                  <button type="button" onClick={() => setAttempt(Date.now())}>
                    重新加载
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
        <div className="ms-actions">
          <p className="ms-hint">
            <MoveHorizontal aria-hidden="true" size={17} />
            拖动旋转，双指缩放
          </p>
          {status === "ready" && (
            <div className="ms-tools" role="group" aria-label="样件视角控制">
              <button
                type="button"
                className="ms-icon"
                aria-label="缩小样件"
                title="缩小"
                onClick={() => model.current?.zoom(-2)}
              >
                <Minus size={17} />
              </button>
              <button
                type="button"
                className="ms-icon"
                aria-label="放大样件"
                title="放大"
                onClick={() => model.current?.zoom(2)}
              >
                <Plus size={17} />
              </button>
              <button type="button" onClick={reset}>
                <RotateCcw size={15} />
                复位
              </button>
              {!reduced && (
                <button
                  type="button"
                  aria-pressed={rotating}
                  onClick={() => setRotating((v) => !v)}
                >
                  {rotating ? <Pause size={15} /> : <Play size={15} />}自动旋转
                </button>
              )}
            </div>
          )}
        </div>
        <footer className="ms-foot">
          <button type="button" className="btn forest" onClick={onMake}>
            为它制作模型 <ArrowRight size={15} />
          </button>
        </footer>
      </div>
    </dialog>
  );
}
