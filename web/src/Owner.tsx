import { useEffect } from "react";
import Auth from "./owner/Auth";
import { PetDetail, PetForm, PetList } from "./owner/Pets";
import { Album, OrderDetail, OrderList } from "./owner/Orders";
import { Create, WorkDetail } from "./owner/Studio";
import { Entry, Note, NotFound, Wait } from "./owner/ui";
import { same, useStudio, type Account, type Nav } from "./owner/data";
import "./Owner.css";

export type OwnerProps = {
  view: string;
  navigate: Nav;
  user: Account | null;
  refreshUser: () => Promise<void>;
};

function safeReturn(value: string | null) {
  if (
    !value ||
    !value.startsWith("/") ||
    value.startsWith("//") ||
    value.startsWith("/login") ||
    value.startsWith("/register")
  )
    return "/pets";
  const parsed = new URL(value, window.location.origin);
  return parsed.origin === window.location.origin
    ? parsed.pathname + parsed.search
    : "/pets";
}
export default function Owner({
  view,
  navigate,
  user,
  refreshUser,
}: OwnerProps) {
  const full = new URL(view, window.location.origin);
  const path = full.pathname.replace(/\/$/, "") || "/";
  const search = full.search
    ? full.searchParams
    : new URLSearchParams(window.location.search);
  const { data, error, load } = useStudio(user?.id);
  const authRoute = path === "/login" || path === "/register";
  const destination = safeReturn(search.get("next") || search.get("returnTo"));
  useEffect(() => {
    if (authRoute && user) navigate(destination);
  }, [authRoute, user?.id, destination, navigate]);
  if (!data)
    return (
      <Entry title={authRoute ? "我的账号" : "工作室"}>
        {error ? (
          <>
            <Note error={error} />
            <button className="ow-btn" onClick={() => void load()}>
              重新连接
            </button>
          </>
        ) : (
          <Wait label="正在打开工作室…" />
        )}
      </Entry>
    );
  if (!data.user || authRoute) {
    if (authRoute && user)
      return (
        <Entry title="我的账号">
          <Wait label="正在进入工作室…" />
        </Entry>
      );
    return (
      <Auth
        key={path}
        initialRegister={path === "/register"}
        refreshUser={async () => {
          await refreshUser();
          await load();
        }}
        nav={navigate}
        onReady={() => {
          if (authRoute) navigate(destination);
        }}
      />
    );
  }
  const props = { data, nav: navigate, refresh: load };
  const fragment = path.split("/").filter(Boolean);
  if (path === "/pets/new") return <PetForm key="new-pet" {...props} />;
  if (fragment[0] === "pets" && fragment.length >= 2) {
    const pet = data.pets.find((p) => same(p.id, fragment[1]));
    if (!pet) return <NotFound nav={navigate} />;
    if (fragment[2] === "edit")
      return <PetForm key={"edit-" + pet.id} {...props} pet={pet} />;
    return <PetDetail key={"pet-" + pet.id} {...props} pet={pet} />;
  }
  if (path === "/pets" || path === "/account") return <PetList {...props} />;
  if (path === "/create/portrait" || path === "/create/model")
    return (
      <Create
        key={path + search.toString()}
        {...props}
        kind={path.endsWith("model") ? "model" : "portrait"}
        search={search}
      />
    );
  if (fragment[0] === "works" && fragment[1]) {
    const work = data.works.find((w) => same(w.id, fragment[1]));
    return work ? (
      <WorkDetail key={work.id} work={work} {...props} />
    ) : (
      <NotFound nav={navigate} />
    );
  }
  if (path === "/orders") return <OrderList {...props} />;
  if (fragment[0] === "orders" && fragment[1]) {
    const order = data.orders.find((o) => same(o.id, fragment[1]));
    return order ? (
      <OrderDetail key={order.id} {...props} order={order} />
    ) : (
      <NotFound nav={navigate} />
    );
  }
  if (path === "/album") return <Album {...props} />;
  return <NotFound nav={navigate} />;
}
