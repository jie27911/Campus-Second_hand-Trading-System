# 校园二手交易系统（Campus Trading System）

本项目是一个“校园二手交易 + 多数据库同步演示”的完整系统。

- 业务：二手商品发布/浏览/搜索、收藏、购物车、交易、站内消息、管理端。
- 同步：三数据库异构环境（MySQL Hub + MariaDB Edge + PostgreSQL Edge），边缘库通过触发器写入 `sync_log`，Hub 侧 `sync_core_worker` 轮询消费并复制到其它库；冲突写入 `conflict_records`，管理端可处理。

项目重点：**数据库同步与冲突处理**（包含冲突记录落库、通知、带 token 的处理链接认证、管理端人工定夺与回写同步）。

## 运行方式（Docker Compose，一键启动）

前置：已安装 Docker / Docker Compose。

```bash
# 从零重建（包含数据库 init.sql 重新生效）
docker compose down -v

# 启动全部服务：三库 + 后端网关 + 前端 + 同步 worker
docker compose up -d --build

# 查看日志（可选）
docker compose logs -f gateway
# 同步 worker 日志
docker compose logs -f sync-worker
```

访问入口：
- 前端：http://localhost:5173
- 后端 API：http://localhost:8000

> 数据库端口：MySQL 3306、MariaDB 3307、Postgres 5432（见 docker-compose.yml）。

## 答辩与材料（已准备）

- 答辩流程与逐字稿： [docs/实验报告/答辩稿.md](docs/实验报告/答辩稿.md)
- 项目设计文档（突出同步与冲突）： [docs/实验报告/项目设计文档.md](docs/实验报告/项目设计文档.md)

建议现场答辩演示顺序（10 分钟）：
1) 启动系统并打开 `docker compose logs -f sync-worker`（展示同步在跑）
2) 发布商品（就近写入所属校区库），刷新列表可立即看到
3) 等待同步后在管理端执行高级查询（Hub MySQL 承载 OLAP）
4) 人为制造冲突 → 管理端看到 `conflict_records` → 选择以哪个库为准并解决

> 若 SMTP 未配置，可用 worker 日志展示冲突 token/链接生成与冲突落库。

## 系统架构（简述）

- **mysql（Hub）**：汇聚库/管理面（`sync_configs`、`sync_worker_state`、`conflict_records` 等），对外提供统一查询。
- **mariadb（Edge A）** 与 **postgres（Edge B）**：边缘业务库，写入后由触发器记录变更到 `sync_log`。
- **sync-worker**：运行 `python -m apps.services.sync_core_worker`，轮询边缘库 `sync_log`，按配置扇出同步。
- **gateway**：FastAPI 网关，提供业务 API 与管理端冲突处理 API。

## 同步机制（关键点）

- **变更捕获**：边缘库触发器把 INSERT/UPDATE/DELETE 的 old/new 快照写入 `sync_log`。
- **复制执行**：Hub worker 以游标方式消费 `sync_log`，执行 upsert/delete 到目标库。
- **冲突处理**：检测到版本/向量时钟冲突时写入 `conflict_records`，管理端可标记 resolved 并选择策略。

## 性能优化（高级查询索引）

为满足“复杂 SQL + 数据库端优化”的实验要求，已针对高级查询访问特征建立组合索引（并同步到三库 schema）：
- `items(status, category_id, campus_id)`
- `transactions(status, seller_id, final_amount)`
- `conflict_records(table_name, record_id)`（Hub MySQL）

## 目录结构（保留运行必需）

- backend/：后端 FastAPI + 同步 worker（含 Dockerfile、依赖、服务代码）
- backend/sql/init/：三库初始化 SQL（从零重建必需）
- frontend/：前端 Vue/Vite（含 Dockerfile）
- docs/实验报告/：实验报告材料（方案与实验要求）
- docker-compose.yml：一键启动编排

## 开发说明（可选）

本仓库已做“运行必需文件”瘦身；如需更多测试/数据脚本/SQL 样例，请从历史版本恢复。
