#!/usr/bin/env python3
"""
proxyCodex — 让 Codex 在国内 API 下顺畅运行

将 Codex 的 Responses API 协议转换为国内 AI 提供商的 Chat Completions 协议。
支持 DeepSeek、Kimi (Moonshot) 等提供商。

用法:
    python proxyCodex.py                          # 默认启动（端口 3000）
    python proxyCodex.py --port 8080              # 自定义端口
    python proxyCodex.py --setup                  # 仅配置 Codex，不启动代理
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urlparse

# ── 常量 ──────────────────────────────────────────────────
DEFAULT_PORT = 3000

# 配置文件目录（持久化，exe 运行时也能保存）
CONFIG_DIR = os.path.expanduser("~/.proxyCodex")
os.makedirs(CONFIG_DIR, exist_ok=True)
PROVIDERS_FILE = os.path.join(CONFIG_DIR, "providers.json")

# PyInstaller 打包后默认数据文件在 sys._MEIPASS 下
_BASE_DIR = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
_BUILTIN_PROVIDERS = os.path.join(_BASE_DIR, "providers.json")

CODEX_CONFIG_DIR = os.path.expanduser("~/.codex")
CODEX_CONFIG_FILE = os.path.join(CODEX_CONFIG_DIR, "config.toml")
CODEX_AUTH_FILE = os.path.join(CODEX_CONFIG_DIR, "auth.json")

VERSION = "1.2.0"
BANNER = f"""
╔══════════════════════════════════════════╗
║         proxyCodex v{VERSION}              ║
║  让 Codex 在国内 API 下顺畅运行           ║
╚══════════════════════════════════════════╝
"""


# ── 提供商配置加载 ────────────────────────────────────────
def load_providers():
    """加载 providers.json（优先 ~/.proxyCodex/，其次内置默认）"""
    default = {
        "providers": {
            "deepseek": {
                "name": "DeepSeek",
                "base_url": "https://api.deepseek.com/v1",
                "models": ["deepseek-chat", "deepseek-reasoner", "deepseek-v4-flash", "deepseek-v4-pro"]
            },
            "moonshot": {
                "name": "Kimi (Moonshot)",
                "base_url": "https://api.moonshot.cn/v1",
                "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"]
            }
        },
        "active_provider": "deepseek",
        "api_key": ""
    }

    # 1. 优先读取持久化用户配置
    if os.path.exists(PROVIDERS_FILE):
        with open(PROVIDERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    # 2. 迁移旧配置（从脚本/项目目录复制）
    _old_providers = os.path.join(os.path.dirname(os.path.abspath(__file__)), "providers.json")
    if os.path.exists(_old_providers) and _old_providers != _BUILTIN_PROVIDERS:
        try:
            with open(_old_providers, "r", encoding="utf-8") as f:
                data = json.load(f)
            save_providers(data)
            print(f"[proxyCodex] 已迁移配置到: {PROVIDERS_FILE}")
            return data
        except Exception:
            pass

    # 3. 尝试从内置文件复制（exe 打包目录）
    if os.path.exists(_BUILTIN_PROVIDERS):
        try:
            with open(_BUILTIN_PROVIDERS, "r", encoding="utf-8") as f:
                data = json.load(f)
            save_providers(data)
            return data
        except Exception:
            pass

    # 4. 创建默认配置
    save_providers(default)
    print(f"[proxyCodex] 已创建配置文件: {PROVIDERS_FILE}")
    return default


def save_providers(config):
    """保存 providers.json"""
    with open(PROVIDERS_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def get_active_provider(config):
    """获取当前激活的提供商配置"""
    provider_id = config.get("active_provider", "deepseek")
    provider = config.get("providers", {}).get(provider_id)
    if not provider:
        print(f"[proxyCodex] 错误: 未找到提供商 '{provider_id}'")
        sys.exit(1)
    return provider_id, provider


# ── Codex 自动配置 ────────────────────────────────────────
def setup_codex_config(port, provider_id, provider, api_key):
    """自动配置 Codex 的 config.toml 和 auth.json"""
    os.makedirs(CODEX_CONFIG_DIR, exist_ok=True)

    # 写入 config.toml
    model = provider.get("models", [None])[0]
    toml_content = f"""# proxyCodex 自动生成 — 请勿手动修改
model_provider = "custom"
model = "{model}"
model_reasoning_effort = "medium"
disable_response_storage = true

[model_providers]
[model_providers.custom]
name = "{provider.get('name', '国内 API 代理')}"
base_url = "http://127.0.0.1:{port}/v1"
wire_api = "responses"
requires_openai_auth = true
"""
    with open(CODEX_CONFIG_FILE, "w", encoding="utf-8") as f:
        f.write(toml_content)
    print(f"[proxyCodex] Codex 配置已写入: {CODEX_CONFIG_FILE}")

    # 写入 auth.json
    auth = {"auth_mode": "apikey", "OPENAI_API_KEY": api_key}
    with open(CODEX_AUTH_FILE, "w", encoding="utf-8") as f:
        json.dump(auth, f, ensure_ascii=False, indent=2)
    print(f"[proxyCodex] API Key 已写入: {CODEX_AUTH_FILE}")


def interactive_setup():
    """交互式首次配置"""
    print(BANNER)
    print("首次配置 — 请填写以下信息:\n")

    config = load_providers()

    # 选择提供商
    provider_ids = list(config["providers"].keys())
    print("可用的提供商:")
    for i, pid in enumerate(provider_ids, 1):
        p = config["providers"][pid]
        print(f"  {i}. {p['name']} ({pid})")
    print()

    while True:
        try:
            choice = input(f"请选择 [1-{len(provider_ids)}] (默认 1): ").strip()
            if not choice:
                choice = "1"
            idx = int(choice) - 1
            if 0 <= idx < len(provider_ids):
                break
        except ValueError:
            pass
        print("输入无效，请重试")

    provider_id = provider_ids[idx]
    provider = config["providers"][provider_id]

    # 输入 API Key
    api_key = input(f"请输入 {provider['name']} API Key: ").strip()
    while not api_key:
        print("API Key 不能为空")
        api_key = input(f"请输入 {provider['name']} API Key: ").strip()

    # 保存配置
    config["active_provider"] = provider_id
    config["api_key"] = api_key
    save_providers(config)

    # 配置 Codex
    setup_codex_config(DEFAULT_PORT, provider_id, provider, api_key)

    print(f"\n✅ 配置完成！当前提供商: {provider['name']}")
    print(f"   现在运行 proxyCodex 即可使用 Codex")


# ── 模型配置 ──────────────────────────────────────────────
def build_model_config(providers_config):
    """从 providers.json 构建 MODEL_CONFIG"""
    config = {}
    pid = providers_config.get("active_provider", "deepseek")
    provider = providers_config.get("providers", {}).get(pid, {})
    base_url = provider.get("base_url", "https://api.deepseek.com/v1")
    provider_name = provider.get("name", "Unknown")
    models = provider.get("models", [])

    for model in models:
        config[model] = {
            "base_url": base_url,
            "provider": provider_name,
            "api_model": model,
        }
    return config


# ── HTTP 服务器 ────────────────────────────────────────────
class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """多线程 HTTP 服务器"""
    allow_reuse_address = True
    daemon_threads = True


class ProxyHandler(BaseHTTPRequestHandler):
    """Responses API → Chat Completions API 代理处理器"""

    # 类级别配置（由 main 设置）
    model_config = {}
    api_key = ""

    # ── 路由 ──
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/v1/models":
            return self._handle_models()
        self._send_error(404, "Not found")

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/v1/responses":
            return self._handle_responses()
        self._send_error(404, "Not found")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    # ── GET /v1/models ──
    def _handle_models(self):
        models = [
            {"id": mid, "object": "model", "created": 1700000000, "owned_by": cfg["provider"]}
            for mid, cfg in self.model_config.items()
        ]
        data = json.dumps({"object": "list", "data": models}).encode("utf-8")
        self._send_json(data)

    # ── POST /v1/responses ──
    def _handle_responses(self):
        content_len = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_len))

        model = body.get("model", "")
        cfg = self.model_config.get(model)

        # 未知模型 → 使用第一个可用模型兜底
        if not cfg and self.model_config:
            fallback_model = list(self.model_config.keys())[0]
            print(f"[proxyCodex] 未知模型 '{model}'，使用 '{fallback_model}' 兜底")
            model = fallback_model
            cfg = self.model_config[model]
        elif not cfg:
            return self._send_error(400, f"未知模型: {model}")

        # API Key 来源：请求头 > 类配置
        api_key = self.headers.get("Authorization", "").replace("Bearer ", "").strip()
        if not api_key:
            api_key = self.__class__.api_key
        if not api_key:
            return self._send_error(401, "缺少 API Key，请先运行 --setup 配置")

        provider_base = cfg["base_url"]
        api_model = cfg.get("api_model", model)

        # 构建 Chat Completions 请求
        messages = self._build_messages(body)
        chat_payload = {
            "model": api_model,
            "messages": messages,
            "stream": False,  # 始终非流式（性能优化）
        }
        for key in ("temperature", "max_tokens", "top_p", "frequency_penalty", "presence_penalty"):
            if key in body:
                chat_payload[key] = body[key]
        if "max_output_tokens" in body:
            chat_payload["max_tokens"] = body["max_output_tokens"]

        # 转发 tools / tool_choice（支持 computer_use 等插件）
        if "tools" in body:
            chat_payload["tools"] = body["tools"]
        if "tool_choice" in body:
            chat_payload["tool_choice"] = body["tool_choice"]

        # 决定响应方式
        stream = body.get("stream", False)

        # 转发
        self._forward(provider_base, chat_payload, api_key, stream, model)

    def _build_messages(self, body):
        """将 Responses API 的 input + instructions 转为 Chat messages"""
        messages = []

        # instructions → system
        if body.get("instructions"):
            instr = body["instructions"]
            if isinstance(instr, list):
                texts = []
                for part in instr:
                    if isinstance(part, dict) and part.get("type") in ("text", "input_text"):
                        texts.append(part.get("text", ""))
                instr = "\n".join(texts)
            messages.append({"role": "system", "content": instr})

        # input → messages
        inp = body.get("input", "")
        if isinstance(inp, str):
            messages.append({"role": "user", "content": inp})
        elif isinstance(inp, list):
            for msg in inp:
                if isinstance(msg, dict):
                    role = msg.get("role", "user")
                    if role == "developer":
                        role = "system"
                    elif role == "assistant":
                        # 保留 assistant 消息（含可能已有的 tool_calls）
                        chat_msg = {"role": "assistant"}
                        content = msg.get("content", "")
                        if isinstance(content, list):
                            texts = []
                            for part in content:
                                if isinstance(part, dict) and part.get("type") in ("text", "input_text"):
                                    texts.append(part.get("text", ""))
                            content = "\n".join(texts)
                        if content:
                            chat_msg["content"] = content
                        # 检查是否已有 tool_calls（多轮对话中复用）
                        if msg.get("tool_calls"):
                            chat_msg["tool_calls"] = msg["tool_calls"]
                        messages.append(chat_msg)
                        continue

                    content = msg.get("content", "")
                    if isinstance(content, list):
                        texts = []
                        for part in content:
                            if isinstance(part, dict) and part.get("type") in ("text", "input_text"):
                                texts.append(part.get("text", ""))
                        content = "\n".join(texts)

                    if role == "tool":
                        # tool 结果消息
                        tool_msg = {"role": "tool", "content": content}
                        if msg.get("tool_call_id"):
                            tool_msg["tool_call_id"] = msg["tool_call_id"]
                        messages.append(tool_msg)
                    elif content:
                        messages.append({"role": role, "content": content})
                elif isinstance(msg, str):
                    messages.append({"role": "user", "content": msg})

        return messages

    # ── 转发 ──
    def _forward(self, provider_base, payload, api_key, stream, model):
        url = f"{provider_base}/chat/completions"
        data = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )

        try:
            resp = urllib.request.urlopen(req, timeout=120)
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="replace")
            return self._send_error(e.code, f"API 错误: {err}")
        except Exception as e:
            return self._send_error(502, f"请求失败: {str(e)}")

        if stream:
            self._handle_streaming(resp, model)
        else:
            self._handle_non_streaming(resp, model)

    # ── 非流式响应（含 tool_calls 支持）──
    def _handle_non_streaming(self, resp, model):
        chat_resp = json.loads(resp.read())
        choice = chat_resp.get("choices", [{}])[0]
        msg = choice.get("message", {})
        content = msg.get("content", "")

        output = []
        # 文本输出
        if content:
            output.append({
                "type": "message",
                "role": msg.get("role", "assistant"),
                "content": [{"type": "output_text", "text": content}],
            })
        # tool_calls 输出
        tool_calls = msg.get("tool_calls", [])
        for tc in tool_calls:
            func = tc.get("function", {})
            output.append({
                "type": "function_call",
                "id": tc.get("id", f"call_{os.urandom(8).hex()}"),
                "name": func.get("name", ""),
                "arguments": func.get("arguments", "{}"),
                "status": "completed",
            })

        responses_resp = {
            "id": f"resp_{chat_resp.get('id', 'unknown')}",
            "object": "response",
            "model": model,
            "status": "completed",
            "output": output,
            "usage": chat_resp.get("usage", {}),
        }
        self._send_json(json.dumps(responses_resp).encode("utf-8"))

    # ── 流式响应（SSE，含 tool_calls）──
    def _handle_streaming(self, resp, model):
        chat_resp = json.loads(resp.read())
        choice = chat_resp.get("choices", [{}])[0]
        msg = choice.get("message", {})
        content = msg.get("content", "")
        tool_calls = msg.get("tool_calls", [])

        # SSE 响应头
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        response_id = f"resp_{os.urandom(8).hex()}"
        item_id = f"item_{os.urandom(8).hex()}"
        created = int(time.time())
        role = msg.get("role", "assistant")

        def sse(event, data):
            try:
                self.wfile.write(f"event: {event}\r\ndata: {json.dumps(data)}\r\n\r\n".encode("utf-8"))
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

        # 构造所有 output items
        output_items = []
        if content:
            output_items.append({
                "id": item_id, "type": "message",
                "role": role, "status": "completed",
                "content": [{"type": "output_text", "text": content}],
            })
        for tc in tool_calls:
            func = tc.get("function", {})
            call_id = tc.get("id", f"call_{os.urandom(8).hex()}")
            output_items.append({
                "id": call_id, "type": "function_call",
                "name": func.get("name", ""),
                "arguments": func.get("arguments", "{}"),
                "status": "completed",
            })

        if not output_items:
            output_items.append({
                "id": item_id, "type": "message",
                "role": role, "status": "completed",
                "content": [{"type": "output_text", "text": ""}],
            })

        # 发送初始化 + 文本 delta
        sse("response.created", {"type":"response.created","id":response_id,"object":"response","created":created,"model":model})
        sse("response.in_progress", {"type":"response.in_progress","id":response_id,"object":"response","created":created,"model":model,"status":"in_progress"})

        out_idx = 0
        if content:
            sse("response.output_item.added", {"type":"response.output_item.added","id":response_id,"object":"response","output_index":0,"item":{"id":item_id,"type":"message","role":role,"status":"in_progress"}})
            sse("response.content_part.added", {"type":"response.content_part.added","id":response_id,"object":"response","output_index":0,"content_index":0,"part":{"type":"text"}})
            if content:
                sse("response.output_text.delta", {"type":"response.output_text.delta","id":response_id,"object":"response","output_index":0,"content_index":0,"delta":content})
            sse("response.output_text.done", {"type":"response.output_text.done","id":response_id,"object":"response","output_index":0,"content_index":0,"text":content})
            sse("response.output_item.done", {"type":"response.output_item.done","id":response_id,"object":"response","output_index":0,"item":output_items[0]})
            out_idx = 1

        # tool_calls 事件
        for i, tc in enumerate(tool_calls):
            func = tc.get("function", {})
            call_id = tc.get("id", f"call_{os.urandom(8).hex()}")
            idx = out_idx + i
            sse("response.output_item.added", {"type":"response.output_item.added","id":response_id,"object":"response","output_index":idx,"item":{"id":call_id,"type":"function_call","name":func.get("name",""),"status":"in_progress"}})
            sse("response.output_item.done", {"type":"response.output_item.done","id":response_id,"object":"response","output_index":idx,"item":output_items[out_idx + i]})

        usage = chat_resp.get("usage", {})
        sse("response.response.done", {"type":"response.response.done","id":response_id,"object":"response","created":created,"model":model,"status":"completed","output":output_items,"usage":usage})

        self.close_connection = True

    # ── 辅助 ──
    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_error(self, code, message):
        data = json.dumps({"error": {"message": message}}).encode("utf-8")
        self._send_json(data, code)

    def log_message(self, fmt, *args):
        print(f"[proxyCodex] {args[0]} {args[1]} {args[2]}")


# ── 入口 ──────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="proxyCodex — 让 Codex 在国内 API 下顺畅运行",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python proxyCodex.py              # 默认启动
  python proxyCodex.py --setup      # 首次配置
  python proxyCodex.py --port 8080  # 自定义端口
        """
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"监听端口 (默认: {DEFAULT_PORT})")
    parser.add_argument("--setup", action="store_true", help="首次交互式配置")
    parser.add_argument("--version", action="store_true", help="显示版本号")

    args = parser.parse_args()

    if args.version:
        print(f"proxyCodex v{VERSION}")
        return

    # 加载配置
    config = load_providers()

    # --setup 模式
    if args.setup:
        interactive_setup()
        return

    # 检查 API Key 是否已配置
    api_key = config.get("api_key", "")
    if not api_key:
        print("[proxyCodex] 首次运行，进入配置模式...")
        interactive_setup()
        config = load_providers()
        api_key = config.get("api_key", "")

    if not api_key:
        print("[proxyCodex] 错误: API Key 未配置，请运行 --setup")
        sys.exit(1)

    # 构建模型配置
    provider_id, provider = get_active_provider(config)
    ProxyHandler.model_config = build_model_config(config)
    ProxyHandler.api_key = api_key

    # 自动配置 Codex（覆盖写入以确保同步）
    setup_codex_config(args.port, provider_id, provider, api_key)

    # 启动服务器
    server = ThreadedHTTPServer(("127.0.0.1", args.port), ProxyHandler)

    print(BANNER)
    print(f"  提供商:     {provider['name']}")
    print(f"  监听地址:   http://127.0.0.1:{args.port}")
    print(f"  可用模型:   {len(ProxyHandler.model_config)} 个")
    print(f"  Codex 配置: {CODEX_CONFIG_FILE}")
    print()
    print("  启动 Codex 桌面版，选择\"国内 API 代理\"即可使用")
    print("  按 Ctrl+C 停止")
    print("=" * 42)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[proxyCodex] 已停止")
        server.server_close()


if __name__ == "__main__":
    main()
