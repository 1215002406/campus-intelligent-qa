# 校园智能问答系统

基于 FastAPI、Vue 3 和 MySQL 的校园知识库问答系统。项目支持多格式文档入库、向量与 BM25 混合检索、引用校验、多轮对话，以及本地或 OpenAI 兼容远程大模型。

## 功能

- Vue 3、TypeScript、Vite、Element Plus 和 Pinia 前端
- FastAPI、SQLAlchemy 2.x 和 MySQL 8.4 后端
- Argon2id 密码哈希、JWT 身份认证和管理员权限控制
- PDF、DOCX、XLSX、CSV、TXT、Markdown 文档解析与切片
- BGE-small 与 Qwen3-Embedding 双向量索引
- 向量检索、中文 BM25 和 RRF 融合排序
- SSE 流式问答、多轮问题改写和引用来源校验
- 本地模型与 OpenAI 兼容远程模型配置切换
- 后端自动化测试和前端生产构建检查

## 技术栈

| 模块 | 主要技术 |
| --- | --- |
| 前端 | Vue 3、TypeScript、Vite、Element Plus、Pinia |
| 后端 | Python 3.11、FastAPI、Pydantic、SQLAlchemy |
| 数据库 | MySQL 8.4 |
| 检索 | Chroma、Sentence Transformers、jieba、BM25 |
| 模型 | Qwen3.8、Qwen3-Embedding、BGE-small |

## 环境要求

- Windows PowerShell 5.1 或 PowerShell 7
- Python 3.11
- Node.js 20.19 或更新版本
- MySQL 8.4

模型文件、数据库内容、上传文档和向量索引不包含在仓库中。运行完整问答功能前，需要按 [backend/.env.example](backend/.env.example) 配置模型和数据库。

## 安装

在项目根目录执行：

```powershell
.\scripts\Setup.ps1
.\scripts\Configure.ps1
```

`Setup.ps1` 会创建 `.venv`、安装后端和前端依赖，并在需要时启动本机 MySQL。

`Configure.ps1` 会交互式填写管理员凭据、生成 JWT 密钥并写入本地 `backend/.env`。如果已有 `DATABASE_URL`，脚本会保留其中受保护的数据库凭据；否则会提示输入 MySQL 应用账号密码。

自定义 MySQL 安装位置时，可以设置：

```powershell
$env:CAMPUS_MYSQLD_PATH = "C:\path\to\mysqld.exe"
$env:CAMPUS_MYSQL_CONFIG_PATH = "C:\path\to\my.ini"
```

## 启动

分别在两个终端中运行：

```powershell
.\scripts\Start-Backend.ps1
```

```powershell
.\scripts\Start-Frontend.ps1
```

服务地址：

- 前端：<http://127.0.0.1:5173>
- 后端接口文档：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/api/health>

## 配置

将 `backend/.env.example` 复制为 `backend/.env` 后填写所需字段。核心配置包括：

- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`
- `ADMIN_REGISTRATION_CODE`
- `JWT_SECRET_KEY`
- `DATABASE_URL`
- `LLM_PROVIDER` 与对应的模型配置
- `EMBEDDING_PROFILE` 与对应的模型路径

本地模型路径默认指向被 Git 忽略的 `data/models/`。也可以在 `backend/.env` 中填写本机绝对路径：

```dotenv
LLM_LOCAL_MODEL=D:/models/qwen3.8-27b.gguf
EMBEDDING_BGE_PATH=D:/models/bge-small-zh-v1.5
EMBEDDING_QWEN_PATH=D:/models/Qwen3-Embedding-0.6B
```

## 测试

运行后端测试和前端生产构建：

```powershell
.\scripts\Test.ps1
```

后端测试默认基于 `backend/.env` 中的 `DATABASE_URL` 连接同主机上的 `campus_qa_test` 数据库。也可以在 CI 中显式设置：

```powershell
$env:CAMPUS_TEST_DATABASE_URL = "mysql+pymysql://<user>:<password>@127.0.0.1:3306/campus_qa_test?charset=utf8mb4"
```

测试会重建测试数据库中的表，不要将其指向业务数据库。

## 目录

```text
.
├── backend/
│   ├── app/                 # API、业务逻辑、检索与模型适配
│   ├── tests/               # 后端自动化测试
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/                 # Vue 页面、组件、路由和状态
│   ├── package.json
│   └── package-lock.json
├── scripts/                 # 安装、配置、启动和测试脚本
├── data/                    # 本地运行数据，模型和索引不提交
└── uploads/                 # 本地上传文件，不提交
```

## 数据与安全

- 仓库不包含 `.env`、真实上传文档、MySQL 数据、向量索引或模型文件。
- 管理员密码只以 Argon2id 哈希形式保存到数据库。
- JWT 保存在浏览器 `sessionStorage`，后端会再次校验权限和资源归属。
- 只应公开经过脱敏的演示数据，不要提交学生个人信息或未经授权的校园文档。
- 本项目默认绑定 `127.0.0.1`，不能直接作为公网部署方案。
