import { lazy, Suspense, useState } from "react";
import {
  ArrowDown,
  ArrowUpRight,
  BookOpen,
  Box,
  Check,
  ChevronRight,
  Image as ImageIcon,
  Leaf,
  MoveHorizontal,
  Rotate3D,
  Paintbrush,
  PawPrint,
  PencilLine,
} from "lucide-react";
import { money } from "./common";
import PhotoCompare from "./PhotoCompare";
import Gallery from "./home/Gallery";
import "./home.css";

const ModelSample = lazy(() => import("./home/ModelSample"));

function scrollToSection(id: string) {
  document.getElementById(id)?.scrollIntoView({
    behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
      ? "instant"
      : "smooth",
    block: "center",
  });
}

export default function Home({
  navigate,
  prices,
}: {
  navigate: (s: string) => void;
  prices: { portrait: number; model: number };
}) {
  const [art, setArt] = useState<"watercolor" | "pencil">("watercolor");
  const [sampleOpen, setSampleOpen] = useState(false);
  function tryPortrait() {
    document
      .querySelector<HTMLInputElement>("#hero-art input[type=range]")
      ?.focus({ preventScroll: true });
    scrollToSection("hero-art");
  }
  return (
    <main className="studio">
      <section className="hero" aria-labelledby="hero-title">
        <div className="hero-copy">
          <div className="hero-kicker">
            <span className="kicker-rule" />
            <Leaf size={15} strokeWidth={1.7} />
            宠物纪念工作室
          </div>
          <h1 id="hero-title">
            把它的模样，
            <br />
            <em>留在时光里。</em>
          </h1>
          <p>
            从一张熟悉的照片开始，为它留下一幅肖像，
            <br className="wide-br" />
            或一份可以捧在手心的立体纪念。
          </p>
          <div className="hero-actions">
            <button
              className="btn forest"
              onClick={() => navigate("/pets/new")}
            >
              <PawPrint size={17} />
              为它建立档案
            </button>
            <button
              className="hero-more"
              onClick={() => scrollToSection("gallery")}
            >
              看看作品 <ArrowDown size={15} />
            </button>
          </div>
        </div>
        <figure className="hero-art" id="hero-art">
          <PhotoCompare
            className="hero-comparison"
            before={{
              src: "/media/meadow.webp",
              alt: "午后的草地上，橘白猫靠在金毛犬身边的原照",
              label: "原照",
            }}
            after={{
              src: "/media/meadow-" + art + ".webp",
              alt:
                art === "watercolor"
                  ? "同一张猫狗合影的水彩肖像"
                  : "同一张猫狗合影的铅绘肖像",
              label: "肖像",
            }}
            fit="cover"
            position="85% 50%"
            initial={52}
            label="拖动分隔线比较猫狗原照与肖像"
          />
          <figcaption className="hero-art-tools">
            <span className="hero-art-hint">
              <MoveHorizontal size={16} />
              拖动对照
            </span>
            <div
              className="art-choices"
              role="group"
              aria-label="首页示例画风"
              data-active={art}
            >
              {(["watercolor", "pencil"] as const).map((value) => (
                <button
                  key={value}
                  type="button"
                  aria-pressed={art === value}
                  onClick={() => setArt(value)}
                >
                  {value === "watercolor" ? (
                    <Paintbrush size={14} />
                  ) : (
                    <PencilLine size={14} />
                  )}
                  {value === "watercolor" ? "水彩" : "铅绘"}
                </button>
              ))}
            </div>
          </figcaption>
        </figure>
      </section>
      <section className="offerings" aria-labelledby="offer-title">
        <div className="section-head">
          <div>
            <h2 id="offer-title">选一份属于它的纪念</h2>
            <p>一张照片，两种收藏它的方式。</p>
          </div>
        </div>
        <div className="service-grid">
          {[
            {
              id: "portrait",
              name: "纪念肖像",
              img: "portrait",
              icon: <PencilLine size={17} />,
              desc: "把熟悉的神态画进水彩与笔触里，\n看过预览，再收藏喜欢的那一张。",
              action: "制作肖像",
              price: prices.portrait,
            },
            {
              id: "model",
              name: "3D 纪念模型",
              img: "studio-corgi-preview",
              icon: <Box size={17} />,
              desc: "从不同角度记住它的模样，\n收藏可旋转、可打印的立体模型。",
              action: "制作模型",
              price: prices.model,
            },
          ].map((s) => (
            <article key={s.id} className={"service-card " + s.id}>
              <div className="service-picture">
                <img
                  src={"/media/" + s.img + ".webp"}
                  alt={
                    s.id === "portrait"
                      ? "橘白猫的水彩肖像"
                      : "橡木纹底座上微微歪头的暖橘柯基样件"
                  }
                />
                <button
                  className="service-preview"
                  type="button"
                  onClick={
                    s.id === "portrait"
                      ? tryPortrait
                      : () => setSampleOpen(true)
                  }
                >
                  {s.id === "portrait" ? (
                    <MoveHorizontal size={14} />
                  ) : (
                    <Rotate3D size={15} />
                  )}
                  {s.id === "portrait" ? "试试画风" : "旋转看样"}
                </button>
              </div>
              <div className="service-body">
                <span className="service-type">
                  {s.icon}
                  <span>{s.id === "portrait" ? "平面艺术" : "立体收藏"}</span>
                </span>
                <h3>{s.name}</h3>
                <p>{s.desc}</p>
                <div className="service-bottom">
                  <strong>
                    <small>¥</small>
                    {money(s.price)}
                  </strong>
                  <button onClick={() => navigate("/create/" + s.id)}>
                    {s.action}
                    <ArrowUpRight size={16} />
                  </button>
                </div>
              </div>
            </article>
          ))}
        </div>
      </section>
      <Gallery navigate={navigate} />
      <section className="how">
        <div>
          <BookOpen size={24} />
          <h2>从照片到收藏</h2>
        </div>
        <ol>
          <li>
            <PawPrint />
            上传宠物照片
          </li>
          <li>
            <ImageIcon />
            对照预览，选定作品
          </li>
          <li>
            <Check />
            存入你的私有相册
          </li>
        </ol>
        <button onClick={() => navigate("/pets/new")}>
          开始建档 <ChevronRight size={16} />
        </button>
      </section>
      {sampleOpen && (
        <Suspense
          fallback={
            <p className="sample-loading" role="status">
              正在打开 3D 样件…
            </p>
          }
        >
          <ModelSample
            onClose={() => setSampleOpen(false)}
            onMake={() => {
              setSampleOpen(false);
              navigate("/create/model");
            }}
          />
        </Suspense>
      )}
    </main>
  );
}
