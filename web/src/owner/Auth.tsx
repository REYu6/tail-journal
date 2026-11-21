import { useState, type FormEvent } from "react";
import { ArrowRight, Eye, EyeOff, Leaf, LockKeyhole } from "lucide-react";
import { api, useAction, type Nav } from "./data";
import { Note } from "./ui";

export default function Auth({
  initialRegister,
  refreshUser,
  onReady,
  nav,
}: {
  initialRegister: boolean;
  refreshUser: () => Promise<void>;
  onReady: () => void;
  nav: Nav;
}) {
  const [register, setRegister] = useState(initialRegister);
  const [show, setShow] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const action = useAction();
  function submit(e: FormEvent) {
    e.preventDefault();
    void action.run(async () => {
      await api(
        "/auth/" + (register ? "register" : "login"),
        "POST",
        register
          ? { email: email.trim(), password, name: name.trim() }
          : { email: email.trim(), password },
      );
      await refreshUser();
    }, onReady);
  }
  return (
    <main className="ow-auth">
      <div className="ow-auth-card">
        <div className="ow-auth-photo">
          <img src="/media/meadow.webp" alt="在自然光里陪伴着的小动物" />
          <div>
            <Leaf size={19} />
            <p>尾巴手记</p>
          </div>
        </div>
        <section className="ow-auth-form">
          <h1>{register ? "创建你的账号" : "欢迎回来"}</h1>
          <p>
            {register
              ? "为它留一份只属于你们的宠物档案。"
              : "登录后，继续查看和制作它的纪念作品。"}
          </p>
          <div className="ow-tabs" aria-label="账号操作">
            <button
              className={!register ? "is-current" : ""}
              type="button"
              onClick={() => {
                setRegister(false);
                action.setError("");
              }}
            >
              登录
            </button>
            <button
              className={register ? "is-current" : ""}
              type="button"
              onClick={() => {
                setRegister(true);
                action.setError("");
              }}
            >
              注册
            </button>
          </div>
          <form onSubmit={submit} className="ow-form">
            {register && (
              <label>
                你的称呼
                <input
                  required
                  value={name}
                  maxLength={60}
                  autoComplete="nickname"
                  onChange={(e) => setName(e.target.value)}
                  placeholder="想让我们怎么称呼你"
                />
              </label>
            )}
            <label>
              邮箱
              <input
                type="email"
                required
                value={email}
                maxLength={254}
                autoComplete="username"
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
              />
            </label>
            <label>
              密码
              <div className="ow-password">
                <input
                  type={show ? "text" : "password"}
                  required
                  value={password}
                  minLength={register ? 8 : 1}
                  autoComplete={register ? "new-password" : "current-password"}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={register ? "至少 8 个字符" : "请输入密码"}
                />
                <button
                  type="button"
                  aria-label={show ? "隐藏密码" : "显示密码"}
                  onClick={() => setShow(!show)}
                >
                  {show ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </label>
            <Note error={action.error} />
            <button disabled={action.busy} className="ow-btn">
              {action.busy ? "正在处理…" : register ? "创建账号" : "登录"}
              <ArrowRight size={17} />
            </button>
          </form>
          <p className="ow-privacy">
            <LockKeyhole size={13} />
            宠物照片和相册默认仅自己可见。
          </p>
          <button className="ow-link" onClick={() => nav("/")}>
            先回工作室看看
          </button>
        </section>
      </div>
    </main>
  );
}
