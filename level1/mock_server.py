# ============================================================
#  level1 配套 · 本地假模型服务器
# ============================================================
#
#  这个文件是"脚手架"，不是学习对象。直接用，不用改。
#
#  它假装自己是一个 OpenAI 兼容的 API 服务器。
#  你的 llm.py 会像调真模型一样，真的发 HTTP 请求、真的收状态码、
#  真的解析 JSON —— 只不过目标是 127.0.0.1，不走外网。
#
#  所以：内网也能做 level1。
#  回家之后，只要把 llm.py 里的 base_url 从
#      http://127.0.0.1:8000
#  改成
#      https://api.deepseek.com
#  就变成真的调模型了。
#
#  只用标准库，不需要 pip install 任何东西。
#
#  ── 怎么启动 ──────────────────────────────────────────────
#      在一个窗口里：
#          python mock_server.py
#      然后另开一个窗口跑 llm.py / check.py。Ctrl+C 停止。
#
#  ── 怎么选模式 ────────────────────────────────────────────
#      靠请求里的 model 字段。想测哪种情况就传哪个 model 名：
#
#        mock-normal   正常返回
#        mock-slow     睡 3 秒再返回          → 测超时
#        mock-timeout  睡 30 秒               → 测超时
#        mock-429      返回 429 限流          → 测退避重试
#        mock-500      返回 500 服务端错误    → 测重试
#        mock-401      返回 401 认证失败      → 测"不该重试"
#        mock-badjson  返回 200，但 JSON 是坏的 → 测解析失败
#        mock-empty    返回 200，但内容是空字符串
#        mock-refuse   返回 200，内容是拒答
#        mock-flaky    同一个 model 名前 2 次 500，第 3 次成功 → 测重试真的有效
#
#      匹配规则是"前缀"，所以你可以传 mock-flaky-abc123 这种带后缀的名字，
#      这样每次跑都是一个全新的计数器（check.py 就是这么用的）。
#
# ============================================================


import json
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


# ------------------------------------------------------------
# 配置
# ------------------------------------------------------------
HOST = "127.0.0.1"
PORT = 8000
REQUEST_LOG = "mock_requests.jsonl"     # 服务器收到过哪些请求，都记在这里


# ------------------------------------------------------------
# 计数器：记录每个 model 名被调用了几次
# mock-flaky 靠这个判断"这是第几次"
# ------------------------------------------------------------
call_counter = {}
counter_lock = threading.Lock()


def bump_counter(model):
    """给这个 model 名的计数加一，返回加完之后的值"""
    with counter_lock:
        if model in call_counter:
            call_counter[model] = call_counter[model] + 1
        else:
            call_counter[model] = 1
        return call_counter[model]


class MockHandler(BaseHTTPRequestHandler):

    # 关掉默认的访问日志（它太吵），我们自己打印
    def log_message(self, format, *args):
        return

    # --------------------------------------------------------
    # 收到 POST 请求
    # --------------------------------------------------------
    def do_POST(self):
        # 1. 读请求体
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)

        try:
            request = json.loads(raw.decode("utf-8"))
        except Exception:
            self.reply_json(400, {"error": {"message": "请求体不是合法 JSON"}})
            return

        model = request.get("model", "mock-normal")
        messages = request.get("messages", [])
        if len(messages) > 0:
            prompt = messages[-1].get("content", "")
        else:
            prompt = ""

        # 2. 记一笔：这样你能事后数"客户端到底发了几次请求"
        n = bump_counter(model)
        with counter_lock:
            f = open(REQUEST_LOG, "a", encoding="utf-8")
            f.write(json.dumps({
                "ts": time.time(),
                "model": model,
                "nth_call_for_this_model": n,
                "prompt": prompt[:60],
            }, ensure_ascii=False) + "\n")
            f.close()

        print("[mock] 第 " + str(n) + " 次收到 model=" + model)

        # 3. 按 model 名前缀决定怎么回
        #    注意：全部用 startswith，这样带后缀的名字也能匹配
        if model.startswith("mock-timeout"):
            time.sleep(30)
            self.reply_ok("（睡了 30 秒才回）")
            return

        if model.startswith("mock-slow"):
            time.sleep(3)
            self.reply_ok("（睡了 3 秒才回）")
            return

        if model.startswith("mock-429"):
            self.reply_json(429,
                            {"error": {"message": "rate limit exceeded",
                                       "type": "rate_limit_exceeded"}},
                            extra_headers={"Retry-After": "2"})
            return

        if model.startswith("mock-500"):
            self.reply_json(500,
                            {"error": {"message": "internal server error",
                                       "type": "server_error"}})
            return

        if model.startswith("mock-401"):
            self.reply_json(401,
                            {"error": {"message": "invalid api key",
                                       "type": "authentication_error"}})
            return

        if model.startswith("mock-badjson"):
            # 故意返回一段被截断的 JSON
            self.reply_raw(200, '{"choices": [{"message": {"content": "被截断了'.encode("utf-8"))
            return

        if model.startswith("mock-empty"):
            self.reply_ok("")          # 内容是空字符串
            return

        if model.startswith("mock-refuse"):
            self.reply_ok("很抱歉，我无法回答这个问题。")
            return

        if model.startswith("mock-flaky"):
            # 前两次失败，第三次成功
            if n <= 2:
                self.reply_json(500,
                                {"error": {"message": "temporary failure",
                                           "type": "server_error"}})
                return
            self.reply_ok("（前两次都失败了，这是第 " + str(n) + " 次，成功了）")
            return

        # 默认：正常返回
        self.reply_ok("数据库索引是一种加快查询速度的数据结构，类似书的目录。")

    # --------------------------------------------------------
    # 三个回复工具
    # --------------------------------------------------------
    def reply_raw(self, status, data):
        """直接回一段原始字节"""
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def reply_json(self, status, obj, extra_headers=None):
        """回一个 JSON"""
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        if extra_headers is not None:
            for key in extra_headers:
                self.send_header(key, extra_headers[key])
        self.end_headers()
        self.wfile.write(data)

    def reply_ok(self, text):
        """回一个"看起来像真 API"的成功响应"""
        body = {
            "id": "chatcmpl-mock",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "mock",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 12,
                "completion_tokens": len(text),
                "total_tokens": 12 + len(text),
            },
        }
        self.reply_json(200, body)


# ------------------------------------------------------------
# 启动
# ------------------------------------------------------------
if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), MockHandler)

    print("=" * 58)
    print("  假模型服务器已启动")
    print("=" * 58)
    print("  地址： http://" + HOST + ":" + str(PORT))
    print("  请求记录会写到：" + REQUEST_LOG)
    print("")
    print("  现在另开一个窗口跑： python check.py")
    print("  收到请求会打印一行。Ctrl+C 停止。")
    print("=" * 58)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("")
        print("已停止。")
