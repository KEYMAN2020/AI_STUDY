# ============================================================
#  level1 验收测试 —— 让这里面所有检查都"通过"，level1 就算过关
# ============================================================
#
#  怎么跑：
#      窗口 1： python mock_server.py     ← 先启动假服务器
#      窗口 2： python check.py
#
#  这个文件是"脚手架"，不是学习对象。你不用改它。
#  它测的是你写在 llm.py 里的 call_model()。
#
# ============================================================


import os
import sys
import json
import uuid

# 保证 calls.jsonl 落在本文件所在目录，而不是你当前所在的目录
HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)

from llm import call_model      # noqa: E402


# ------------------------------------------------------------
# 记分
# ------------------------------------------------------------
passed = 0
failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed = passed + 1
        print("    [通过] " + name + (("   " + detail) if detail else ""))
    else:
        failed = failed + 1
        print("    [失败] " + name + (("   " + detail) if detail else ""))
    return condition


def run(name, func):
    """跑一个测试段，顺便兜住"还没实现"的异常"""
    print("")
    print(name)
    try:
        func()
    except NotImplementedError as e:
        global failed
        failed = failed + 1
        print("    [失败] llm.py 里还有没写完的 TODO：" + str(e))
    except Exception as e:
        failed = failed + 1
        print("    [失败] 抛出了意料之外的异常：" + type(e).__name__ + ": " + str(e))


def new_flaky_name():
    """每次都生成一个全新的假模型名，这样服务器端的计数器是干净的"""
    return "mock-flaky-" + uuid.uuid4().hex[:6]


# ------------------------------------------------------------
# 开始
# ------------------------------------------------------------
print("=" * 60)
print("  level1 验收测试")
print("=" * 60)


# ------------------------------------------------------------
# 0. 先确认假服务器在跑
# ------------------------------------------------------------
print("")
print("0. 连通性检查")

try:
    probe = call_model("测试", model="mock-normal", timeout=3)
    server_up = probe.get("ok", False) is True
except Exception as e:
    server_up = False
    print("    连不上假服务器：" + type(e).__name__ + ": " + str(e))

if server_up:
    check("假服务器已启动，能正常通信", True)
else:
    check("假服务器已启动", False,
          "→ 请先在另一个窗口运行 python mock_server.py")
    print("")
    print("  后面的测试没法继续了。先启动 mock_server.py 再重跑本文件。")
    sys.exit(1)


# ------------------------------------------------------------
# 1. 正常路径
# ------------------------------------------------------------
def test_normal():
    r = call_model("你好", model="mock-normal")
    check("ok 为 True", r.get("ok") is True, "实际 " + str(r.get("ok")))
    check("text 非空", bool(r.get("text")), "实际 " + repr(r.get("text")))
    check("error_type 为 None", r.get("error_type") is None,
          "实际 " + str(r.get("error_type")))
    check("attempts == 1", r.get("attempts") == 1, "实际 " + str(r.get("attempts")))
    check("in_tokens > 0", (r.get("in_tokens") or 0) > 0,
          "实际 " + str(r.get("in_tokens")))
    check("out_tokens > 0", (r.get("out_tokens") or 0) > 0,
          "实际 " + str(r.get("out_tokens")))
    check("latency_ms 是个正数", (r.get("latency_ms") or 0) > 0,
          "实际 " + str(r.get("latency_ms")))
    check("request_id 非空", bool(r.get("request_id")))


run("1. 正常路径（mock-normal）", test_normal)


# ------------------------------------------------------------
# 2. 超时
# ------------------------------------------------------------
def test_timeout():
    # mock-slow 会睡 3 秒，我们只给它 1 秒
    r = call_model("你好", model="mock-slow", timeout=1, max_retries=0)
    check("ok 为 False", r.get("ok") is False)
    check("error_type == timeout", r.get("error_type") == "timeout",
          "实际 " + str(r.get("error_type")))
    check("text 为 None", r.get("text") is None)
    check("attempts == 1（max_retries=0，不许重试）",
          r.get("attempts") == 1, "实际 " + str(r.get("attempts")))


run("2. 超时（mock-slow 睡 3 秒，timeout 只给 1 秒）", test_timeout)


# ------------------------------------------------------------
# 3. 认证失败 —— 不该重试
# ------------------------------------------------------------
def test_auth():
    r = call_model("你好", model="mock-401", max_retries=3)
    check("ok 为 False", r.get("ok") is False)
    check("error_type == auth", r.get("error_type") == "auth",
          "实际 " + str(r.get("error_type")))
    check("attempts == 1（认证失败重试没意义，不该重试）",
          r.get("attempts") == 1, "实际 " + str(r.get("attempts")))


run("3. 认证失败（mock-401，max_retries=3）", test_auth)


# ------------------------------------------------------------
# 4. 服务端 500 —— 应该重试
# ------------------------------------------------------------
def test_server_error():
    r = call_model("你好", model="mock-500", max_retries=2)
    check("ok 为 False", r.get("ok") is False)
    check("error_type == server", r.get("error_type") == "server",
          "实际 " + str(r.get("error_type")))
    check("attempts == 3（1 次请求 + 2 次重试）",
          r.get("attempts") == 3, "实际 " + str(r.get("attempts")))


run("4. 服务端错误（mock-500，max_retries=2）", test_server_error)


# ------------------------------------------------------------
# 5. 限流 429 —— 应该重试
# ------------------------------------------------------------
def test_rate_limit():
    r = call_model("你好", model="mock-429", max_retries=1)
    check("ok 为 False", r.get("ok") is False)
    check("error_type == rate_limit", r.get("error_type") == "rate_limit",
          "实际 " + str(r.get("error_type")))
    check("attempts >= 2（限流应该重试）",
          (r.get("attempts") or 0) >= 2, "实际 " + str(r.get("attempts")))


run("5. 限流（mock-429，max_retries=1）", test_rate_limit)


# ------------------------------------------------------------
# 6. 坏 JSON
# ------------------------------------------------------------
def test_bad_json():
    r = call_model("你好", model="mock-badjson", max_retries=0)
    check("ok 为 False", r.get("ok") is False)
    check("error_type == parse", r.get("error_type") == "parse",
          "实际 " + str(r.get("error_type")))


run("6. 坏 JSON（mock-badjson，服务器返回被截断的 JSON）", test_bad_json)


# ------------------------------------------------------------
# 7. 空回答
# ------------------------------------------------------------
def test_empty():
    r = call_model("你好", model="mock-empty", max_retries=0)
    check("ok 为 False（空回答不算成功）", r.get("ok") is False)
    check("error_type == parse", r.get("error_type") == "parse",
          "实际 " + str(r.get("error_type")))


run("7. 空回答（mock-empty，HTTP 200 但内容是空字符串）", test_empty)


# ------------------------------------------------------------
# 8. 重试真的能救回来
# ------------------------------------------------------------
def test_flaky():
    name = new_flaky_name()
    print("    （本次使用全新模型名 " + name + "，确保前两次一定失败）")
    r = call_model("你好", model=name, max_retries=3)
    check("ok 为 True（第三次成功了）", r.get("ok") is True,
          "实际 " + str(r.get("ok")))
    check("attempts == 3", r.get("attempts") == 3,
          "实际 " + str(r.get("attempts")))
    check("text 非空", bool(r.get("text")))
    check("error_type 为 None（最终成功了）", r.get("error_type") is None,
          "实际 " + str(r.get("error_type")))


run("8. 重试真的能救回来（mock-flaky：前 2 次 500，第 3 次成功）", test_flaky)


# ------------------------------------------------------------
# 9. calls.jsonl 有没有记全
# ------------------------------------------------------------
def test_log():
    log_path = os.path.join(HERE, "calls.jsonl")
    check("calls.jsonl 文件存在", os.path.exists(log_path))

    if not os.path.exists(log_path):
        return

    lines = open(log_path, "r", encoding="utf-8").read().splitlines()
    lines = [ln for ln in lines if ln.strip() != ""]

    check("里面有记录（至少 9 条）", len(lines) >= 9, "实际 " + str(len(lines)))

    required = ["ts", "request_id", "model", "in_tokens", "out_tokens",
                "latency_ms", "ok", "error_type", "attempts"]

    # 检查最后一条的字段
    try:
        last = json.loads(lines[-1])
    except Exception as e:
        check("最后一行是合法 JSON", False, str(e))
        return

    check("最后一行是合法 JSON", True)

    missing = []
    for key in required:
        if key not in last:
            missing.append(key)

    check("字段齐全", len(missing) == 0, ("缺少 " + str(missing)) if missing else "")

    # 检查失败的那几次有没有被记成 ok=false
    bad_ok_count = 0
    for ln in lines:
        try:
            rec = json.loads(ln)
        except Exception:
            continue
        if rec.get("ok") is False:
            bad_ok_count = bad_ok_count + 1

    check("失败的那几次也被记下来了", bad_ok_count > 0,
          "ok=false 的记录有 " + str(bad_ok_count) + " 条")


run("9. 调用日志（calls.jsonl）", test_log)


# ------------------------------------------------------------
# 汇总
# ------------------------------------------------------------
print("")
print("=" * 60)
print("  结果：" + str(passed) + " 项通过，" + str(failed) + " 项失败")
print("=" * 60)

if failed == 0:
    print("")
    print("  level1 的工程部分过关了。")
    print("  而且注意：刚才这些全部是在**不联网**的情况下测出来的。")
    print("")
    print("  下一步：回家把 llm.py 顶部的 BASE_URL 改成真地址，")
    print("  跑一遍真实调用，看看真实模型的失败率和延迟。")
else:
    print("")
    print("  还有 " + str(failed) + " 项没通过。改 llm.py，然后重跑。")
    print("")
    print("  提示：假服务器的窗口会打印每次收到的请求，")
    print("        可以对照着看'客户端到底发了几次请求'。")

sys.exit(0 if failed == 0 else 1)
