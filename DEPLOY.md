# 部署尾巴手记

本项目用一个应用容器同时提供前台、管理页面、API 和后台任务。默认使用本地 SQLite、私有文件卷和演示服务。Docker 镜像构建时会把 3D 查看器的 Draco、KTX2 和 Meshopt 解码文件一起打包。用户查看模型时直接从本站加载这些文件。

## 在本机用 Docker 运行

准备 Docker Engine 和 Compose 2.20 以上版本。首次构建需要访问 npm、PyPI 和基础镜像仓库。到项目根目录执行：

```sh
docker compose config --quiet
docker compose up --build -d --wait
docker compose exec app python -m server.manage create-user --email admin@example.com --role admin
```

第三条命令交互式设置你的管理员密码。请用自己的邮箱。运营账号将角色参数改为 `operator`。网站通过 [本地工作室](http://localhost:8000/) 访问，管理人员通过[管理后台](http://localhost:8000/admin)登录。健康探针为 [/api/health](http://localhost:8000/api/health)。退出或重建应用容器后，命名卷 `pet-data` 继续保存数据库和文件。

若 8000 端口已被其他程序使用，在根目录 `.env` 设置 `PET_HTTP_PORT=8080` 和 `PET_PUBLIC_URL=http://localhost:8080`。Compose 会读取该文件。部署凭证只在服务端填写，限制 `.env` 对其他用户的读权限。

## 切换成公开服务

1. 绑定自己的域名和 HTTPS 证书，让同机反向代理将请求转发到 `127.0.0.1:8000`。前台、API、下载和支付回调共用这个域名。若代理在独立容器或另一台主机，按实际私网拓扑调整访问方式。
2. 在部署环境设置 `PET_PUBLIC_URL=https://你的域名`。这会启用 Secure 会话 cookie，并生成对应的收银台返回地址。代理保留请求的 Host 和原始协议，向应用转发真实客户端 IP。将 `FORWARDED_ALLOW_IPS` 设置为实际可信代理地址，以便登录限流识别访问者。
3. 在真实收费前准备模型、收款账号和私有存储，在独立测试环境验证一笔照片订单、一笔 3D 订单以及退款。每项服务可以独立选择演示或真实模式。付款环境应与模型商品标识一致，公开收费请使用真实生成服务。
4. 配置变更后执行 `docker compose up -d --build --wait` 重新创建服务。后台按持久化任务状态继续处理。

同机 Caddy 的最小配置示例：

```caddyfile
pets.example.com {
    request_body {
        max_size 12MB
    }
    reverse_proxy 127.0.0.1:8000
}
```

### 服务配置

| 能力 | 环境变量 | 开通与验证 |
|---|---|---|
| 百炼图片编辑 | `PET_IMAGE_MODE=live`、`DASHSCOPE_API_KEY` | 默认模型 `qwen-image-2.1-turbo`。切换模型可设置 `QWEN_IMAGE_MODEL`，应选择支持参考图、异步编辑及所需输出张数的模型。默认使用北京服务域名。若使用百炼的业务空间专用域名，将 `DASHSCOPE_BASE_URL` 设为该 HTTPS **域名根地址**，例如 `https://工作空间ID.cn-beijing.maas.aliyuncs.com`，由应用附加路径。API Key 与地域要匹配。[百炼 API 说明](https://help.aliyun.com/zh/model-studio/qwen-image-generation-and-editing-api-reference) |
| fal 建模 | `PET_MODEL_MODE=live`、`FAL_KEY` | 采用 Meshy 7.1 队列接口，一张原照走单图，多张原照走多视图。GLB 没有附带 STL 时，应用从同一模型转换出 80 mm 高的 STL。交付仍需主人确认和运营质检。[模型接口](https://fal.ai/models/fal-ai/meshy/v7.1/image-to-3d/api) · [fal 队列](https://fal.ai/docs/documentation/model-apis/inference/queue) |
| Stripe 支付 | `PET_PAYMENT_MODE=stripe`、`STRIPE_SECRET_KEY`、`STRIPE_WEBHOOK_SECRET`、HTTPS 的 `PET_PUBLIC_URL` | 用商户自己的 Stripe 账户开通 Checkout。订单币种为 CNY，付款方式取决于商户账户所在地区、业务资质和 Dashboard 配置。目标客户在中国大陆时，应先核对商户是否可开户，再核对可向客户显示的支付方式。支付宝通过 Stripe 的可用性受能力审核影响。[商户地区](https://stripe.com/global) · [支付宝能力](https://docs.stripe.com/payments/alipay) |
| 对象存储 | `PET_S3_BUCKET`、`PET_S3_REGION`、必要时设置 `PET_S3_ENDPOINT` | 支持 S3 及兼容签名 V4 的端点，包含使用 S3 兼容接口的 OSS。桶须为私有。应用使用标准 AWS 凭证链，支持实例角色，或 `AWS_ACCESS_KEY_ID`、`AWS_SECRET_ACCESS_KEY` 和可选的 `AWS_SESSION_TOKEN`。服务账号需有 `private/` 前缀对象的读写删除权限。模型服务需要能读取输入图片的临时签名 URL。 |

真实模式缺少凭证时后台任务会报错。遇到供应商是否已受理不明确的任务，先在供应商控制台核对任务 ID，再通过管理后台恢复查询，以免产生第二次调用费用。

### 配置与核对支付回调

在 Stripe Workbench 创建事件端点 `https://你的域名/api/payments/webhook`，填入该端点对应的签名密钥。测试环境使用测试账户密钥与测试端点的签名密钥，两者要配套。选择：

- `checkout.session.completed`、`checkout.session.async_payment_succeeded`、`checkout.session.async_payment_failed`、`checkout.session.expired`。
- `refund.created`、`refund.updated`、`refund.failed`。

代理应转发原始请求体和 `Stripe-Signature` 请求头。校准服务器时间，验签窗口为 5 分钟。浏览器从支付页回站后，可以在订单页刷新状态；应用依据验签成功的事件确认付款。测试重发时使用 Stripe 后台的重发功能产生新的投递签名，同一事件 ID 只处理一次。核对回调状态、订单金额、原支付凭证和退款最终状态。公开收款还需完成自己的商户审批、生产回调配置和真实环境验收。[Stripe Webhook 文档](https://docs.stripe.com/webhooks)

### 选用 PostgreSQL

SQLite 适合本机及单实例试点。新环境可以直接启用 Compose 的 PostgreSQL 服务。先用 `openssl rand -hex 32` 生成一个随机密码，在根目录的私有 `.env` 写入以下两项，替换第一行的占位内容：

```dotenv
PET_POSTGRES_PASSWORD=替换为刚生成的十六进制密码
DATABASE_URL=postgresql://petstudio:${PET_POSTGRES_PASSWORD}@db:5432/petstudio
```

执行 `docker compose --profile postgres up --build -d --wait`。数据库只在 Compose 私有网络内提供服务，数据保存在 `pet-postgres` 卷。也可将 `DATABASE_URL` 设置为已有 PostgreSQL 的连接串，再用默认的 `docker compose up`。切换数据库会连接到新的数据集；有历史订单的 SQLite 环境应先备份、迁移并核对记录后再切流。对象存储也遵循同样原则，已有媒体需要按原文件标识复制到新存储的 `private/` 前缀。

## 备份与恢复

备份需要同时覆盖订单数据库、私有媒体和部署配置。建议把加密备份写到独立存储，并在独立实例中实际恢复一份。以下命令以使用本地文件卷的 Compose 为例，备份文件应存放在管理员的私有目录。

```sh
umask 077
docker compose stop app
docker compose run -T --rm --no-deps app python -c 'import sys,tarfile; t=tarfile.open(fileobj=sys.stdout.buffer,mode="w|gz"); t.add("/var/lib/pet-studio", arcname="."); t.close()' > pet-data.tar.gz
docker compose up -d app --wait
```

使用 PostgreSQL 时，在停应用之后、重新启动前，额外执行 `docker compose exec -T db pg_dump -Fc -U petstudio petstudio > petstudio.pgcustom`，并用带 `--profile postgres` 的 Compose 命令重新启动应用。使用私有桶时，请另为 `private/` 的全部对象做备份或保存可恢复版本。仅恢复数据库无法找回照片和模型。

恢复到**新项目名和空卷**时，先在独立目录准备同一版配置和镜像。以下示例将本地文件归档解包到新项目卷，遇到非空目录会立即退出：

```sh
docker compose -p tail-journal-restore run -T --rm --no-deps app python -c 'import pathlib,sys,tarfile; p=pathlib.Path("/var/lib/pet-studio"); assert not any(p.iterdir()), "需要空卷"; t=tarfile.open(fileobj=sys.stdin.buffer,mode="r|gz"); t.extractall(p,filter="data")' < pet-data.tar.gz
```

PostgreSQL 用新项目启动空数据库，使用 `pg_restore --no-owner --exit-on-error -U petstudio -d petstudio` 将 `petstudio.pgcustom` 恢复到该库。新实例用独立端口和演示支付验证一份宠物档案、一个购买记录与实际下载，再决定是否把域名指向新实例。

## 两节点网络课设

在项目根目录运行以下命令。协调器、节点 A 和节点 B 使用同一个应用镜像，各自运行在独立容器中。节点通过协调器的私有 HTTP 接口取文件并上传结果。存储和数据库仅由协调器访问。

```sh
export PET_NODE_TOKEN="$(openssl rand -hex 32)"
docker compose -f docker-compose.yml -f compose.network.yml up --build -d --wait
```

同一部署的节点和协调器使用相同的 `PET_NODE_TOKEN`。重新部署时可以从自己的私有环境配置加载该值。若是新数据库，使用管理命令创建后台账号：

```sh
docker compose exec app python -m server.manage create-user --email admin@example.org --role admin
```

打开管理后台的「节点调度」，等两台节点显示在线。用主人账号上传照片并支付一笔演示建模订单，即可观察工作节点领取任务，交付结果继续进入原有的看样、质检流程。故障演示时可用 `docker compose -f docker-compose.yml -f compose.network.yml stop worker-a` 停止节点 A，用同一命令的 `start worker-a` 子命令恢复。已领取的任务在租约失效后方可接管，仍在排队的任务会根据在线节点重新分配。

跨主机运行时，将协调器部署在各节点可达的 HTTPS 地址。协调器环境设置 `PET_DISTRIBUTED=1` 和 `PET_NODE_TOKEN`。各工作机安装项目 Python 依赖后，设置相同的节点令牌、唯一的 `PET_NODE_ID` 和 `PET_COORDINATOR_URL`，运行 `python -m server.processing_node`。如使用反向代理，允许 `PUT /api/processing/tasks/{job_id}/result` 上传最大 200 MiB 的模型结果。回到单机模式前，在后台确认当前分布式任务已处理完毕。实验脚本、指标定义和样例数据见[网络实验说明](docs/NETWORK_LAB.md)。
