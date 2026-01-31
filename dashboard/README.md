# Trader Dashboard

AI Trader 系统的 Web Dashboard。

## 快速开始

### 1. 安装依赖

```bash
cd dashboard
npm install
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```env
DATABASE_URL=postgresql://user:password@localhost:5432/trader
SESSION_SECRET=your-session-secret-at-least-32-characters
DASHBOARD_PASSWORD=your-secure-password
```

### 3. 初始化数据库

```bash
npm run db:push
```

### 4. 启动开发服务器

```bash
npm run dev
```

访问 http://localhost:3000

## 技术栈

- **框架**: Remix (React Router v7)
- **UI**: shadcn/ui + Tailwind CSS
- **数据库**: PostgreSQL + Drizzle ORM
- **图表**: TradingView Lightweight Charts + Recharts

## 目录结构

```
dashboard/
├── app/
│   ├── components/     # UI 组件
│   ├── hooks/          # React Hooks
│   ├── lib/            # 工具函数
│   ├── routes/         # 页面路由
│   └── services/       # 服务层
├── db/
│   ├── schema.ts       # 数据库表定义
│   └── migrations/     # 数据库迁移
└── public/             # 静态资源
```

## 数据库命令

```bash
# 生成迁移
npm run db:generate

# 执行迁移
npm run db:migrate

# 推送 schema（开发用）
npm run db:push

# 打开数据库管理界面
npm run db:studio
```
