# 第三方组件与 License 声明

> 赛题 04 · 团队：TBD · 由 `submission/gen_third_party.py` 生成后复制。

# 第三方组件清单

> 由 `submission/gen_third_party.py` 生成，请勿手改；依赖变化后重新生成。
> 后端为 `ocft-backend/requirements.txt` 的运行时依赖闭包（不含 pytest 等测试依赖），前端为 `ocft-starter/package.json` 的直接依赖。License 读自安装后的包元数据。

| 组件 | 版本 | License | 用途 | 范围 | 来源 |
|------|------|---------|------|------|------|
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause | 解密 .env 中的密文配置 | 后端运行时（直接依赖） | https://github.com/pyca/cryptography |
| fastapi | 0.157.0 | MIT | HTTP 框架 | 后端运行时（直接依赖） | https://github.com/fastapi/fastapi |
| langchain-core | 1.6.13 | MIT | LangGraph 的依赖，本仓库不直接调用 | 后端运行时（直接依赖） | https://docs.langchain.com/ |
| langgraph | 1.2.16 | MIT | 调度 model / tools 两个节点的下一跳（ADR-0004） | 后端运行时（直接依赖） | https://docs.langchain.com/oss/python/langgraph/overview |
| openai | 3.35.1 | Apache-2.0 | 以 OpenAI 兼容协议调用 deepseek-v4.1-flash（只负责 HTTP 传输） | 后端运行时（直接依赖） | https://github.com/openai/openai-python |
| openpyxl | 3.1.5 | MIT | 批量测评读写 xlsx | 后端运行时（直接依赖） | https://foss.heptapod.net/openpyxl/openpyxl |
| pydantic | 2.14.1 | MIT | 请求 / 响应模型校验 | 后端运行时（直接依赖） | https://github.com/pydantic/pydantic |
| pydantic-settings | 2.16.1 | MIT | 配置加载 | 后端运行时（直接依赖） | https://github.com/pydantic/pydantic-settings |
| PyMySQL | 1.2.3 | MIT | MySQL 驱动 | 后端运行时（直接依赖） | https://pypi.org/project/PyMySQL/ |
| PyYAML | 6.0.3 | MIT | 读取 config.yaml | 后端运行时（直接依赖） | https://github.com/yaml/pyyaml |
| redis | 8.1.0 | MIT | Redis 客户端 | 后端运行时（直接依赖） | https://github.com/redis/redis-py |
| socksio | 1.0.0 | MIT License | SOCKS 代理连接支持 | 后端运行时（直接依赖） | https://github.com/sethmlarson/socksio |
| SQLAlchemy | 2.1.5 | MIT | ORM / 数据库访问 | 后端运行时（直接依赖） | https://www.sqlalchemy.org |
| sqlglot | 30.24.0 | MIT | sql_query 工具的 SQL 语法树只读校验 | 后端运行时（直接依赖） | https://sqlglot.com/ |
| uvicorn | 0.54.0 | BSD-3-Clause | ASGI 服务器 | 后端运行时（直接依赖） | https://uvicorn.dev/ |
| annotated-doc | 0.0.5 | MIT | 传递依赖 | 后端运行时 | https://github.com/fastapi/annotated-doc |
| annotated-types | 0.8.0 | MIT | 传递依赖 | 后端运行时 | https://github.com/annotated-types/annotated-types |
| anyio | 4.15.1 | MIT | 传递依赖 | 后端运行时 | https://github.com/agronholm/anyio |
| certifi | 2026.10.19 | MPL-2.0 | 传递依赖 | 后端运行时 | https://github.com/certifi/python-certifi |
| cffi | 2.1.1 | MIT-0 | 传递依赖 | 后端运行时 | https://github.com/python-cffi/cffi |
| charset-normalizer | 3.5.2 | MIT | 传递依赖 | 后端运行时 | https://pypi.org/project/charset-normalizer/ |
| click | 8.5.0 | BSD-3-Clause | 传递依赖 | 后端运行时 | https://github.com/pallets/click/ |
| distro | 1.9.0 | Apache License, Version 2.0 | 传递依赖 | 后端运行时 | https://github.com/python-distro/distro |
| et_xmlfile | 2.0.0 | MIT | 传递依赖 | 后端运行时 | https://foss.heptapod.net/openpyxl/et_xmlfile |
| h11 | 0.16.0 | MIT | 传递依赖 | 后端运行时 | https://github.com/python-hyper/h11 |
| httpcore | 1.0.9 | BSD-3-Clause | 传递依赖 | 后端运行时 | https://www.encode.io/httpcore/ |
| httpcore2 | 2.16.0 | BSD-3-Clause | 传递依赖 | 后端运行时 | https://github.com/pydantic/httpx2 |
| httptools | 0.9.0 | MIT | 传递依赖 | 后端运行时 | https://github.com/MagicStack/httptools |
| httpx | 0.28.1 | BSD-3-Clause | 传递依赖 | 后端运行时 | https://github.com/encode/httpx |
| httpx2 | 2.16.0 | BSD-3-Clause | 传递依赖 | 后端运行时 | https://github.com/pydantic/httpx2 |
| idna | 3.20 | BSD-3-Clause | 传递依赖 | 后端运行时 | https://github.com/kjd/idna |
| jiter | 0.17.0 | MIT | 传递依赖 | 后端运行时 | https://github.com/pydantic/jiter/ |
| jsonpatch | 1.36 | BSD-3-Clause | 传递依赖 | 后端运行时 | https://github.com/stefankoegl/python-json-patch.git |
| jsonpointer | 3.4 | Modified BSD License | 传递依赖 | 后端运行时 | https://github.com/stefankoegl/python-json-pointer |
| langchain-protocol | 0.0.20 | MIT | 传递依赖 | 后端运行时 | https://github.com/langchain-ai/agent-protocol/tree/main/streaming |
| langgraph-checkpoint | 4.3.0 | MIT | 传递依赖 | 后端运行时 | https://github.com/langchain-ai/langgraph/tree/main/libs/checkpoint |
| langgraph-prebuilt | 1.1.1 | MIT | 传递依赖 | 后端运行时 | https://github.com/langchain-ai/langgraph/tree/main/libs/prebuilt |
| langgraph-sdk | 0.4.8 | MIT | 传递依赖 | 后端运行时 | https://github.com/langchain-ai/langgraph/tree/main/libs/sdk-py |
| langsmith | 0.14.12 | MIT | 传递依赖 | 后端运行时 | https://github.com/langchain-ai/langsmith-python |
| opentelemetry-api | 1.45.1 | Apache-2.0 | 传递依赖 | 后端运行时 | https://github.com/open-telemetry/opentelemetry-python/tree/main/opentelemetry-api |
| orjson | 3.13.0 | MPL-2.0 AND (Apache-2.0 OR MIT) | 传递依赖 | 后端运行时 | https://github.com/ijl/orjson |
| ormsgpack | 1.13.0 | Apache-2.0 OR MIT | 传递依赖 | 后端运行时 | https://github.com/ormsgpack/ormsgpack |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | 传递依赖 | 后端运行时 | https://github.com/pypa/packaging |
| pycparser | 3.11 | BSD-3-Clause | 传递依赖 | 后端运行时 | https://github.com/eliben/pycparser |
| pydantic_core | 2.50.1 | MIT | 传递依赖 | 后端运行时 | https://github.com/pydantic |
| python-dotenv | 1.2.4 | BSD-3-Clause | 传递依赖 | 后端运行时 | https://github.com/theskumar/python-dotenv |
| requests | 2.34.2 | Apache-2.0 | 传递依赖 | 后端运行时 | https://github.com/psf/requests |
| requests-toolbelt | 1.0.0 | Apache 2.0 | 传递依赖 | 后端运行时 | https://github.com/requests/toolbelt |
| sniffio | 1.3.1 | MIT OR Apache-2.0 | 传递依赖 | 后端运行时 | https://github.com/python-trio/sniffio |
| starlette | 1.9.0 | BSD-3-Clause | 传递依赖 | 后端运行时 | https://github.com/Kludex/starlette |
| tenacity | 9.2.1 | Apache-2.0 | 传递依赖 | 后端运行时 | https://github.com/jd/tenacity |
| truststore | 0.10.5 | MIT | 传递依赖 | 后端运行时 | https://github.com/sethmlarson/truststore |
| typing-inspection | 0.4.4 | MIT | 传递依赖 | 后端运行时 | https://github.com/pydantic/typing-inspection |
| typing_extensions | 4.16.0 | PSF-2.0 | 传递依赖 | 后端运行时 | https://github.com/python/typing_extensions |
| urllib3 | 2.8.0 | MIT | 传递依赖 | 后端运行时 | https://pypi.org/project/urllib3/ |
| uuid_utils | 0.18.0 | BSD-3-Clause | 传递依赖 | 后端运行时 | https://github.com/aminalaee/uuid-utils |
| uvloop | 0.23.0 | MIT License | 传递依赖 | 后端运行时 | https://github.com/MagicStack/uvloop |
| watchfiles | 1.3.0 | MIT | 传递依赖 | 后端运行时 | https://github.com/samuelcolvin/watchfiles |
| websockets | 16.1.1 | BSD-3-Clause | 传递依赖 | 后端运行时 | https://github.com/python-websockets/websockets |
| xxhash | 4.0.2 | BSD-2-Clause | 传递依赖 | 后端运行时 | https://github.com/ifduyue/python-xxhash |
| zstandard | 0.25.0 | BSD-3-Clause | 传递依赖 | 后端运行时 | https://github.com/indygreg/python-zstandard |
| @base-ui/react | 1.9.0 | MIT | 无样式组件底座 | 前端运行时（打包进 dist） | https://github.com/mui/base-ui.git |
| @tailwindcss/vite | 4.3.3 | MIT | Tailwind 构建插件 | 前端运行时（打包进 dist） | https://github.com/tailwindlabs/tailwindcss.git |
| class-variance-authority | 0.7.1 | Apache-2.0 | 组件变体样式 | 前端运行时（打包进 dist） | https://github.com/joe-bell/cva.git |
| cn | 0.5.0 | MIT | class 合并工具 | 前端运行时（打包进 dist） | https://github.com/shadcn-ui/cn.git |
| lucide-react | 1.61.0 | ISC | 图标 | 前端运行时（打包进 dist） | https://github.com/lucide-icons/lucide.git |
| motion | 14.5.0 | MIT | 轨迹入场动效 | 前端运行时（打包进 dist） | https://github.com/motiondivision/motion |
| react | 19.3.1 | MIT | UI 框架 | 前端运行时（打包进 dist） | https://github.com/react/react.git |
| react-dom | 19.3.1 | MIT | UI 渲染 | 前端运行时（打包进 dist） | https://github.com/react/react.git |
| shadcn | 4.22.1 | MIT | 组件样式工具 | 前端运行时（打包进 dist） | https://github.com/shadcn-ui/ui.git |
| tailwindcss | 4.3.3 | MIT | 样式 | 前端运行时（打包进 dist） | https://github.com/tailwindlabs/tailwindcss.git |
| tw-animate-css | 1.4.0 | MIT | 组件动画类 | 前端运行时（打包进 dist） | Wombosvideo/tw-animate-css |
| @types/node | 24.19.2 | MIT | 类型声明 | 前端构建期 | https://github.com/DefinitelyTyped/DefinitelyTyped.git |
| @types/react | 19.3.0 | MIT | 类型声明 | 前端构建期 | https://github.com/DefinitelyTyped/DefinitelyTyped.git |
| @types/react-dom | 19.3.0 | MIT | 类型声明 | 前端构建期 | https://github.com/DefinitelyTyped/DefinitelyTyped.git |
| @vitejs/plugin-react | 6.1.2 | MIT | React 构建插件 | 前端构建期 | https://github.com/vitejs/vite-plugin-react.git |
| oxlint | 1.88.0 | MIT | 代码检查 | 前端构建期 | https://github.com/oxc-project/oxc |
| typescript | 7.0.2 | Apache-2.0 | 类型检查 | 前端构建期 | https://github.com/microsoft/TypeScript.git |
| vite | 8.3.4 | MIT | 前端构建 | 前端构建期 | https://github.com/vitejs/vite.git |

共 79 项。
