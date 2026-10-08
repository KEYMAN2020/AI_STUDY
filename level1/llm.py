# ============================================================
#  level1 主角 —— 把"调用模型"封装成一个可观测、可容错的函数
# ============================================================
#
#  这个文件是学习对象，请你自己把 5 个 TODO 补完。
#  补完之后运行 check.py，让所有检查通过 —— 那就是 level1 的验收。
#
#  ── 核心设计：它不关心"真模型还是假模型" ──────────────────
#
#      这个函数只认 base_url 这一个东西：
#
#        base_url = "http://127.0.0.1:8000"  →  本地假服务器（内网可用）
#        base_url = "https://api.deepseek.com" → 真模型（回家用）
#
#      代码一行都不用改，只改这个常量。这叫"可替换的部件"。
#
#  ── 怎么跑 ────────────────────────────────────────────────
#      窗口 1： python mock_server.py
#      窗口 2： python check.py
#
# ============================================================


import os
import json
import time
import uuid
import urllib.request
import urllib.error

# ------------------------------------------------------------
# 配置
# ------------------------------------------------------------
# ★ 回家之后，把这一行改成 "https://api.deepseek.com"
#   然后把 MODEL 改成 "deepseek-flash"，API_KEY 改成你真 key
BASE_URL = "http://127.0.0.1:8000"
MODEL = "mock-normal"
API_KEY = "sk-mock"

LOG_FILE = "calls.jsonl"     # 每次调用都会往这里追加一行
REQUEST_PATH = "/chat/completions"   # 接口路径

# 超时设几秒。本地测试可以设小一点（比如 1 秒），方便测出超时
DEFAULT_TIMEOUT = 5

# 出现这些错误，重试是有意义的
RETRYABLE_ERRORS = ["timeout", "rate_limit", "server", "network"]

# 出现这些错误，重试毫无意义（比如 key 错了，再试一万次也一样，
# 只会浪费时间、甚至可能把账号锁掉）
FATAL_ERRORS = ["auth", "parse"]


# ------------------------------------------------------------
# 工具函数（这部分已经写好了，直接用）
# ------------------------------------------------------------
def write_log(record):
    """把一次调用记进 calls.jsonl。一行一个 JSON，用追加模式。"""
    f = open(LOG_FILE, "a", encoding="utf-8")
    f.write(json.dumps(record, ensure_ascii=False) + "\n")
    f.close()


def now_ms():
    """当前时间戳，单位毫秒"""
    return int(time.time() * 1000)


# ------------------------------------------------------------
# ★ 主角：调用模型
# ------------------------------------------------------------
def call_model(prompt, temperature=0.0, timeout=DEFAULT_TIMEOUT,
               max_retries=2, model=None, base_url=None):
    """
    调用一次模型。失败会自动重试。

    必须返回这样一个字典：
        {
            "ok":         True / False      这次调用最终成功了吗
            "text":       "模型回答" 或 None  失败时是 None
            "error_type": None 或 字符串      成功时是 None
            "in_tokens":  整数
            "out_tokens": 整数
            "latency_ms": 整数   这次调用总共花了多久（含所有重试的等待）
            "attempts":   整数   实际尝试了几次
            "request_id": 字符串  本次调用的唯一 id
        }

    error_type 的取值必须是下面之一：
        "timeout"     超时
        "auth"        认证失败（401 / 403）
        "rate_limit"  被限流（429）
        "server"      服务端错误（5xx）
        "network"     网络层错误（连不上等）
        "parse"       拿到了响应，但内容不合法（坏 JSON / 空回答）
        "other"       其他
    """
    if model is None:
        model = MODEL
    if base_url is None:
        base_url = BASE_URL

    request_id = uuid.uuid4().hex[:12]
    started = time.time()

    attempts = 0
    last_error_type = None
    last_text = None
    in_tokens = 0
    out_tokens = 0

    while attempts <= max_retries:
        attempts = attempts + 1

        # ====================================================
        # TODO 1 · 发一次请求
        # ====================================================
        # 要求：
        #   1. 拼出完整 URL： base_url + REQUEST_PATH
        #   2. 请求体是一个 JSON，至少包含：
        #        {"model": model,
        #         "messages": [{"role": "user", "content": prompt}],
        #         "temperature": temperature}
        #      提示：json.dumps(那个字典).encode("utf-8")
        #   3. 用 urllib.request.Request(url, data=..., headers=..., method="POST")
        #      headers 至少要有：
        #        "Content-Type": "application/json"
        #        "Authorization": "Bearer " + API_KEY
        #   4. 用 urllib.request.urlopen(req, timeout=timeout) 发出去
        #      ★ timeout 参数一定要传，否则会无限等下去
        #
        # 成功时：你会拿到一个响应对象，用 .read() 拿到 body 的字节
        # 失败时：会抛异常，见 TODO 2

        # ====================================================
        # TODO 2 · 区分成功和失败，并给错误分类
        # ====================================================
        # 用 try / except 包住 TODO 1 的那段。
        #
        # 异常 → error_type 的对应关系：
        #
        #   TimeoutError（Python 3.10+ 的 socket.timeout 就是它）
        #       → "timeout"
        #
        #   urllib.error.HTTPError
        #       这个对象有 .code 属性，就是 HTTP 状态码：
        #         401 或 403  → "auth"
        #         429         → "rate_limit"
        #         500~599     → "server"
        #         其他        → "other"
        #       ★ 注意：429 的响应头里可能有 "Retry-After"，TODO 3 要用
        #
        #   urllib.error.URLError
        #       → "network"
        #       ★ 坑：连接超时有时会被包在 URLError 里，
        #         这时 e.reason 是 TimeoutError。
        #         所以要先判断 isinstance(e.reason, TimeoutError)，
        #         是的话归成 "timeout"，否则才是 "network"。
        #
        # 另外，HTTP 200 也**不一定**代表成功，还要检查 body：
        #   - json.loads 失败（可能被截断了）        → "parse"
        #   - 解析出来但 choices[0].message.content
        #     是 None 或空字符串                      → "parse"
        #   提示：把 json.loads 也放进 try/except 里
        #
        # 成功时，记得把这两个值取出来：
        #   in_tokens  = body["usage"]["prompt_tokens"]
        #   out_tokens = body["usage"]["completion_tokens"]

        # ====================================================
        # TODO 3 · 决定重试还是放弃
        # ====================================================
        # 成功 → 用 break 跳出 while 循环
        #
        # 失败 → 分三种情况：
        #   1. error_type 在 FATAL_ERRORS 里
        #        → 立刻放弃，不要重试，跳出循环
        #
        #   2. error_type 在 RETRYABLE_ERRORS 里，而且还有重试机会
        #        → 等一会儿再试。等待时间用指数退避：
        #            第 1 次失败等 1 秒，第 2 次等 2 秒，第 3 次等 4 秒
        #            提示：wait = 2 ** (attempts - 1)
        #        → ★ 如果服务端返回了 Retry-After 头，优先用它
        #          （mock-429 会返回 Retry-After: 2），
        #          因为服务端比你更清楚该等多久
        #        → 用 time.sleep(wait) 等待
        #
        #   3. 其他情况 → 放弃，跳出循环
        #
        # 循环条件 while attempts <= max_retries 已经在上面写好了，
        # 你只要控制"继续"还是"break"。

        # 临时占位：TODO 补完后把下面这行删掉
        raise NotImplementedError("TODO 1 / 2 / 3 还没写")

    # ========================================================
    # TODO 4 · 把这一次调用写进 calls.jsonl
    # ========================================================
    # 不管成功失败都要记。用已经写好的 write_log()，传一个字典进去。
    # 必须包含这些 key：
    #     ts           时间戳（用 now_ms()）
    #     request_id
    #     model
    #     in_tokens
    #     out_tokens
    #     latency_ms   总共花了多少毫秒（用 time.time() - started 算）
    #     ok           True / False
    #     error_type
    #     attempts
    #
    # 注意：用一个变量记下"这次到底成功了没有"，
    #       别靠 last_error_type 是不是 None 来判断 ——
    #       如果第一次失败、第二次成功，last_error_type 还是会有值。

    # ========================================================
    # TODO 5 · 返回结果字典
    # ========================================================
    # 按前面 docstring 里说的结构返回。
    # 成功时 text 是模型回答、error_type 是 None；
    # 失败时 text 是 None、error_type 是最后一次的错误类别。

    raise NotImplementedError("TODO 4 / 5 还没写")


# ------------------------------------------------------------
# 快速自测：写完一个 TODO 想马上看看效果，就跑这个文件
#    python llm.py
# 完整的验收请跑 check.py
# ------------------------------------------------------------
if __name__ == "__main__":
    print("快速自测：向假服务器发一次请求")
    print("（如果报连接错误，说明 mock_server.py 没启动）")
    print("")

    result = call_model("你好", model="mock-normal")

    print(json.dumps(result, ensure_ascii=False, indent=2))
