# MCP Server 架构解析

这是一个基于 **Model Context Protocol (MCP)** 的脱敏工具服务，使用 **Python asyncio** 异步框架实现。

---

## 1. 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      MCP Client (如 Cursor AI)             │
│                   通过 stdio 与 MCP 服务通信                  │
└─────────────────────────┬───────────────────────────────────┘
                          │ stdio (JSON-RPC)
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              DesensitizationMCPServer                        │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  Server("desensitization-tool")                        │ │
│  │  - list_tools() → 返回可用工具列表                        │ │
│  │  - call_tool() → 分发到具体 handler                      │ │
│  └─────────────────────────────────────────────────────────┘ │
│                            │                                  │
│          ┌─────────────────┼─────────────────┐               │
│          ▼                 ▼                 ▼               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │   Storage    │  │Desensitize   │  │   Handlers   │        │
│  │  (数据存储)   │  │   Engine     │  │ (业务逻辑)    │        │
│  └──────────────┘  │  (脱敏引擎)   │  └──────────────┘        │
│                    └──────────────┘                           │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 核心组件

| 组件 | 文件 | 职责 |
|------|------|------|
| **Server** | `mcp.server.Server` | MCP 协议处理，接收/发送 JSON-RPC |
| **Storage** | `storage.py` | 项目配置、规则、备份的持久化 |
| **DesensitizeEngine** | `desensitize_engine.py` | 具体的脱敏/恢复文件操作 |

---

## 3. 工具注册机制

在 `_setup_handlers()` 中定义所有可用工具：

```python
@srv.list_tools()          # MCP 协议：列出所有工具
async def list_tools() -> list[Tool]:
    return [
        Tool(name="desensitize", ...),
        Tool(name="restore", ...),
        Tool(name="list_projects", ...),
        Tool(name="get_project_rules", ...),
        Tool(name="add_project_rule", ...),
        Tool(name="edit_project_rule", ...),
        Tool(name="delete_project_rule", ...),
        Tool(name="toggle_project_rule", ...),
        Tool(name="add_project", ...),
        Tool(name="delete_project", ...),
    ]

@srv.call_tool()           # MCP 协议：调用具体工具
async def call_tool(name: str, arguments: dict):
    # 分发到对应 handler
    handler = handlers.get(name)
    return await handler(arguments)
```

---

## 4. 工具分类

| 类别 | 工具 | 功能 |
|------|------|------|
| **核心操作** | `desensitize` | 对项目执行脱敏 |
| | `restore` | 恢复脱敏文件 |
| **项目管理** | `list_projects` | 列出所有项目 |
| | `add_project` | 新增项目 |
| | `delete_project` | 删除项目（跳转界面） |
| **规则管理** | `get_project_rules` | 获取规则列表 |
| | `add_project_rule` | 添加规则 |
| | `edit_project_rule` | 编辑规则 |
| | `delete_project_rule` | 删除规则 |
| | `toggle_project_rule` | 启用/禁用规则 |

---

## 5. 生命周期

```
启动 (main.py)
    │
    ▼
start_mcp_server_in_thread(storage)
    │
    ▼
DesensitizationMCPServer.__init__()
    │
    ├── self.storage = storage       # 共享存储实例
    ├── self.engine = DesensitizeEngine()  # 脱敏引擎
    ├── self.server = Server("desensitization-tool")
    └── self._setup_handlers()       # 注册所有工具处理函数
    │
    ▼
_run_server() [async]
    │
    ▼
stdio_server()  ← 启动 stdio 通信循环
    │
    ▼
等待 MCP Client 请求 (常驻内存)
    │
    ├── list_tools()    → 返回工具列表
    └── call_tool()     → 执行具体工具
```

---

## 6. 启动模式

| 模式 | 命令 | 说明 |
|------|------|------|
| **GUI 模式** | 直接运行 `python main.py` | 启动 GUI + MCP 服务（后台线程） |
| **MCP 纯模式** | `python main.py --mcp` | 仅启动 MCP 服务，无界面 |

---

## 7. 关键设计特点

1. **Daemon 线程运行** - MCP 服务在独立 daemon 线程中运行，不阻塞主线程
2. **共享 Storage 实例** - GUI 和 MCP 共用同一个 `Storage` 实例，数据实时同步
3. **别名动态更新** - `_get_alias_schema()` 每次调用时从 `storage` 读取最新别名列表
4. **异常隔离** - `call_tool` 中有 try-except，单个工具出错不影响服务
