import { createRoot } from "react-dom/client";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  lazy,
  Suspense,
} from "react";
import {
  PawPrint,
  UserRound,
  ChevronDown,
  Menu,
  X,
  BookOpen,
  Images,
  ReceiptText,
  LayoutDashboard,
  LogOut,
  MoveUpRight,
  ArrowRight,
} from "lucide-react";
import { api, type SessionUser } from "./common";
import Home from "./Home";
import "./global.css";

const Owner = lazy(() => import("./Owner"));
const Admin = lazy(() => import("./Admin"));

function Brand({ onClick }: { onClick: () => void }) {
  return (
    <a
      className="wordmark"
      href="/"
      onClick={(e) => {
        e.preventDefault();
        onClick();
      }}
      aria-label="尾巴手记首页"
    >
      <img src="/paw.svg" alt="" width="37" height="37" />
      <span>尾巴手记</span>
    </a>
  );
}
function App() {
  const [view, setView] = useState(location.pathname + location.search);
  const [user, setUser] = useState<SessionUser | null>(null);
  const [prices, setPrices] = useState({ portrait: 2990, model: 9900 });
  const [ready, setReady] = useState(false);
  const [connection, setConnection] = useState("");
  const [menu, setMenu] = useState(false);
  const account = useRef<HTMLDivElement>(null);
  const navigate = useCallback((path: string) => {
    if (path !== location.pathname + location.search)
      history.pushState({}, "", path);
    setView(path);
    setMenu(false);
    window.scrollTo(0, 0);
  }, []);
  const refreshUser = useCallback(async () => {
    try {
      const data = await api("/state");
      setUser(data.user || null);
      if (data.prices) setPrices(data.prices);
      setConnection("");
    } catch (err) {
      setConnection(
        err instanceof Error ? err.message : "暂时无法连接工作室。",
      );
    } finally {
      setReady(true);
    }
  }, []);
  useEffect(() => {
    void refreshUser();
    const cb = () => {
      setView(location.pathname + location.search);
      setMenu(false);
    };
    window.addEventListener("popstate", cb);
    return () => window.removeEventListener("popstate", cb);
  }, [refreshUser]);
  useEffect(() => {
    if (!menu) return;
    function outside(e: PointerEvent) {
      if (!account.current?.contains(e.target as Node)) setMenu(false);
    }
    function escape(e: KeyboardEvent) {
      if (e.key === "Escape") setMenu(false);
    }
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [menu]);
  const path = view.split("?")[0];
  useEffect(() => {
    const section = path.startsWith("/admin")
      ? "运营后台"
      : path.startsWith("/pets")
        ? "宠物档案"
        : path.startsWith("/album")
          ? "纪念相册"
          : path.startsWith("/orders")
            ? "我的订单"
            : path.startsWith("/create")
              ? "制作纪念品"
              : path === "/login"
                ? "账户"
                : "宠物纪念工作室";
    document.title = section + " · 尾巴手记";
  }, [path]);
  const links = [
    ["/", "工作室"],
    ["/pets", "宠物档案"],
    ["/album", "纪念相册"],
  ];
  const link = (p: string, name: string, cls = "", icon?: React.ReactNode) => (
    <a
      key={p}
      href={p}
      className={cls}
      onClick={(e) => {
        if (!e.ctrlKey && !e.metaKey) {
          e.preventDefault();
          navigate(p);
        }
      }}
    >
      {icon}
      {name}
    </a>
  );
  return (
    <>
      <a className="skip" href="#main">
        跳到主要内容
      </a>
      <header className="masthead">
        <div className="mast-inner">
          <Brand onClick={() => navigate("/")} />
          <nav className="primary-nav" aria-label="主导航">
            {links.map(([p, n]) =>
              link(
                p,
                n,
                path === p || (p !== "/" && path.startsWith(p + "/"))
                  ? "current"
                  : "",
              ),
            )}
          </nav>
          <div className="header-actions">
            <div className="account" ref={account}>
              {user ? (
                <button
                  className="account-btn"
                  aria-expanded={menu}
                  onClick={() => setMenu(!menu)}
                >
                  <UserRound size={16} />
                  <span>{user.name}</span>
                  <ChevronDown size={13} />
                </button>
              ) : (
                <>
                  {link(
                    "/login",
                    "登录 / 注册",
                    "account-btn visitor-login",
                    <UserRound size={16} />,
                  )}
                  <button
                    className="mobile-menu"
                    aria-label="打开导航"
                    aria-expanded={menu}
                    onClick={() => setMenu(!menu)}
                  >
                    {menu ? <X /> : <Menu />}
                  </button>
                </>
              )}
              {menu && (
                <div className="account-menu">
                  {link("/", "工作室", "mobile-link", <PawPrint size={16} />)}
                  {link("/pets", "宠物档案", "", <BookOpen size={16} />)}
                  {link("/album", "纪念相册", "", <Images size={16} />)}
                  {link("/orders", "我的订单", "", <ReceiptText size={16} />)}
                  {user &&
                    ["admin", "operator"].includes(user.role) &&
                    link(
                      "/admin",
                      "管理后台",
                      "",
                      <LayoutDashboard size={16} />,
                    )}
                  {user ? (
                    <button
                      onClick={async () => {
                        try {
                          await api("/auth/logout", "POST");
                          await refreshUser();
                          navigate("/");
                        } catch (e) {
                          setConnection(String(e));
                        }
                      }}
                    >
                      <LogOut size={16} />
                      退出登录
                    </button>
                  ) : (
                    link("/login", "登录 / 注册", "", <UserRound size={16} />)
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </header>
      <div id="main" className="main-container">
        {connection && (
          <div role="alert" className="connection-error">
            {connection}{" "}
            <button onClick={() => void refreshUser()}>重新连接</button>
          </div>
        )}
        {path === "/" ? (
          <Home navigate={navigate} prices={prices} />
        ) : !ready ? (
          <div className="loading-line">正在打开工作室…</div>
        ) : (
          <Suspense
            fallback={<div className="loading-line">正在打开页面…</div>}
          >
            {path.startsWith("/admin") ? (
              <Admin
                user={user}
                refreshUser={refreshUser}
                navigate={navigate}
              />
            ) : (
              <Owner
                view={view}
                user={user}
                refreshUser={refreshUser}
                navigate={navigate}
              />
            )}
          </Suspense>
        )}
      </div>
      <footer className="site-footer">
        <div>
          <Brand onClick={() => navigate("/")} />
          <small>宠物纪念工作室</small>
        </div>
        <nav aria-label="页脚">
          {link("/orders", "我的订单", "", <ArrowRight size={13} />)}
          {link("/admin", "工作室管理", "", <MoveUpRight size={13} />)}
        </nav>
      </footer>
    </>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
