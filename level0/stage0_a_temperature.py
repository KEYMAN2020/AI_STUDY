# ============================================================
#  level0 · 脚本 A —— temperature 能看见吗？
# ============================================================
#
#  这个脚本做什么：
#      同一句话，用 temperature=1 问 20 次，再用 temperature=0 问 20 次。
#      然后数一数：同样的问题，20 次里出现了几种不同的回答？
#
#  你会看到：
#      temperature=1  →  出现很多种不同说法
#      temperature=0  →  也会出现很多种（这是上一轮的实测结果，
#                        和"理论上应该每次都一样"不符，值得注意）
#
#  怎么跑：
#      先 cd 到本文件所在目录，然后执行
#          python stage0_a_temperature.py
#
# ============================================================


# ------------------------------------------------------------
# 第一步：把要用的工具箱搬进来
# ------------------------------------------------------------
import os      # 用来读环境变量、拼文件路径、建文件夹
import json    # 用来把结果存成 json 文件
import time    # 用来计算每次调用花了多少毫秒

from openai import OpenAI   # 调用大模型的官方工具箱


# ------------------------------------------------------------
# 第二步：参数设置（只有这一块你可以随便改）
# ------------------------------------------------------------
BASE_URL = "https://api.deepseek.com"      # 服务商地址，换别家就改这一行
MODEL = "deepseek-flash"                   # 用哪个模型
PROMPT = "用一句话解释什么是数据库索引。"    # 要问的问题
N = 20                                     # 每个温度问几次
# ------------------------------------------------------------


# ------------------------------------------------------------
# 第三步：搞清楚"本文件所在的文件夹"是哪个
# ------------------------------------------------------------
# __file__        = 这个脚本自己的文件名
# abspath(__file__) = 把它变成完整的绝对路径
# dirname(...)    = 取出它所在的文件夹（去掉文件名）
#
# 这样写的好处：不管你在哪个目录下执行这个脚本，都能正确找到
# 同目录下的 myKey.txt 和 notes 文件夹。
HERE = os.path.dirname(os.path.abspath(__file__))
NOTES_DIR = os.path.join(HERE, "notes")


# ------------------------------------------------------------
# 第四步：找到 API key
# ------------------------------------------------------------
# 找的顺序：先看环境变量，找不到再看同目录的 myKey.txt
API_KEY = os.environ.get("DEEPSEEK_API_KEY")

if API_KEY is None or API_KEY.strip() == "":
    key_file = os.path.join(HERE, "myKey.txt")
    if os.path.exists(key_file):
        f = open(key_file, "r", encoding="utf-8")
        API_KEY = f.read().strip()
        f.close()

if API_KEY is None or API_KEY.strip() == "":
    print("没找到 API key。两种办法，二选一：")
    print('  1. 在 PowerShell 里先执行：$env:DEEPSEEK_API_KEY="sk-你的key"')
    print('  2. 在本目录建一个 myKey.txt，里面只写 key 本身，不要引号')
    raise SystemExit    # 直接结束脚本

# 只显示头几个字符，避免完整 key 被打印到屏幕上或截进图里
print("使用 key ：", API_KEY[:6] + "...")
print("使用模型 ：", MODEL)


# ------------------------------------------------------------
# 第五步：建立一个"客户端"，后面每次调用都靠它
# ------------------------------------------------------------
client = OpenAI(api_key=API_KEY, base_url=BASE_URL)


# ------------------------------------------------------------
# 第六步：定义"问一次"这个动作
# ------------------------------------------------------------
def ask_once(temperature):
    """问一次模型，返回 4 个东西：回答文字、耗时毫秒、输入token、输出token。"""

    start = time.time()          # 记下开始时间

    # ===== 下面这一段就是"调用大模型"的全部 =====
    resp = client.chat.completions.create(
        model=MODEL,

        # messages 是"对话内容"，是一个列表。
        # 每一轮对话是一个字典，role 表示"谁说的"，
        # user 表示用户说的，content 是说的内容。
        messages=[
            {"role": "user", "content": PROMPT}
        ],

        # ★ 整个脚本的主角：随机性开关
        temperature=temperature,
    )
    # ============================================

    cost_ms = (time.time() - start) * 1000     # 算出这次花了多少毫秒

    # 模型回答的文字，藏在这个位置上：
    #   resp                = 整个返回结果
    #   resp.choices        = 候选回答的列表（通常只有一个）
    #   resp.choices[0]     = 第一个候选
    #   .message            = 它的消息
    #   .content            = 消息的文字内容
    text = resp.choices[0].message.content.strip()

    # 这次用了多少 token（token 是模型计费和计长度用的单位）
    in_tokens = resp.usage.prompt_tokens        # 我们发过去的
    out_tokens = resp.usage.completion_tokens   # 模型回给我们的

    return text, cost_ms, in_tokens, out_tokens


# ------------------------------------------------------------
# 第七步：跑一整组（同一个温度，连问 N 次）
# ------------------------------------------------------------
def run_one_temperature(temperature):
    print("")
    print("=" * 56)
    print("  开始跑：temperature =", temperature)
    print("=" * 56)

    answers = []      # 把每次的回答文字存这里
    latencies = []    # 把每次的耗时存这里
    total_in = 0      # 输入 token 合计
    total_out = 0     # 输出 token 合计

    for i in range(N):
        text, cost_ms, in_tok, out_tok = ask_once(temperature)

        answers.append(text)
        latencies.append(cost_ms)
        total_in = total_in + in_tok
        total_out = total_out + out_tok

        # 每跑完一次就打印一行，这样你能看见它在动。
        # text[:40] 表示"只取前 40 个字"，免得一行太长刷屏。
        print("  [" + str(i + 1) + "/" + str(N) + "]  " + text[:40])

    return answers, latencies, total_in, total_out


# ------------------------------------------------------------
# 第八步：数一数"有几种不同的回答"
# ------------------------------------------------------------
# 这里故意不用任何高级工具，就手写一个循环来数，
# 因为这样你能一眼看懂它在干什么。
def count_kinds(answers):
    """返回一个字典：{回答文字: 出现次数}"""
    counts = {}
    for a in answers:
        if a in counts:
            counts[a] = counts[a] + 1      # 见过，次数加一
        else:
            counts[a] = 1                  # 第一次见
    return counts


# ------------------------------------------------------------
# 第九步：把一组的统计结果打印出来
# ------------------------------------------------------------
def report(temperature, answers, latencies, total_in, total_out):
    counts = count_kinds(answers)

    # 算延迟的 P50 和 P95。
    # 先把耗时从小到大排好序，再按位置取。
    latencies.sort()
    p50 = latencies[len(latencies) // 2]                    # 正中间那个
    p95 = latencies[int(len(latencies) * 0.95) - 1]         # 第 95% 位置那个
    slowest = latencies[-1]                                 # 最后一个 = 最慢的

    print("")
    print("  ---------- temperature = " + str(temperature) + " 的结果 ----------")
    print("  问了 " + str(N) + " 次，出现了 " + str(len(counts)) + " 种不同的回答")
    print("  延迟   P50 = " + str(round(p50)) + " ms"
          + "   P95 = " + str(round(p95)) + " ms"
          + "   最慢 = " + str(round(slowest)) + " ms")
    print("  token  输入 " + str(total_in) + "，输出 " + str(total_out)
          + "，合计 " + str(total_in + total_out))
    print("  成本   去 https://api-docs.deepseek.com/zh-cn/quick_start/pricing")
    print("         查单价，乘以上面的 token 数")


# ------------------------------------------------------------
# 第十步：正式开跑
# ------------------------------------------------------------
print("")
print(">>> 第一组：temperature = 1（每次都可能不一样）")
answers_1, lat_1, in_1, out_1 = run_one_temperature(1.0)
report(1.0, answers_1, lat_1, in_1, out_1)

print("")
print(">>> 第二组：temperature = 0（理论上每次都该一样）")
answers_0, lat_0, in_0, out_0 = run_one_temperature(0.0)
report(0.0, answers_0, lat_0, in_0, out_0)


# ------------------------------------------------------------
# 第十一步：把原始数据存下来，后面几个 level 还要用
# ------------------------------------------------------------
os.makedirs(NOTES_DIR, exist_ok=True)     # 没有 notes 文件夹就建一个

data = {
    "temperature_1_answers": answers_1,
    "temperature_0_answers": answers_0,
    "temperature_1_latency_ms": lat_1,
    "temperature_0_latency_ms": lat_0,
}

json_path = os.path.join(NOTES_DIR, "stage0_a_raw.json")
f = open(json_path, "w", encoding="utf-8")
json.dump(data, f, ensure_ascii=False, indent=2)
f.close()


# ------------------------------------------------------------
# 第十二步：把结论打印出来，方便你抄进笔记
# ------------------------------------------------------------
kinds_1 = len(count_kinds(answers_1))
kinds_0 = len(count_kinds(answers_0))

print("")
print("#" * 56)
print("#  记下来")
print("#" * 56)
print("  temperature=1  →  20 次里出现了 " + str(kinds_1) + " 种不同回答")
print("  temperature=0  →  20 次里出现了 " + str(kinds_0) + " 种不同回答")
print("")
print("  原始数据已存到：" + json_path)

print("")
print("-" * 56)
print("  想一想（不用写下来，但要想）：")
print("   1. temperature=0 那一组，20 次真的完全一样吗？")
print("   2. 如果我要跑 50 道题的评测，希望结果可复现，我该用哪个温度？")
print("   3. 如果 temperature=0 也不一样，那我还能靠什么判断")
print("      '这次改动真的有效果'？")
print("-" * 56)
