# ============================================================
#  level0 · 脚本 C —— 验证"为什么 temperature=0 也不确定"
# ============================================================
#
#  背景（这是跑完脚本 A 之后冒出来的问题）：
#      脚本 A 里 temperature=0 的 20 次，得到了 20 种不同的回答。
#      这说明 T=0 并没有给出确定性。为什么？
#
#      两种可能：
#        甲、temperature 确实生效了，但服务端本身有非确定性
#            （模型是"混合专家"结构，还有批处理、GPU 浮点计算顺序等，
#             这些都会带来微小差异），而且这种噪声会随生成长度被放大。
#        乙、temperature=0 被服务端当成了"没传"，实际按默认值 1 在跑。
#
#  这个脚本用两个任务试着把甲和乙分开：
#
#      任务 1（短，只回答一个词）—— 从三个词里选一个
#          如果 T=0 收敛到某一个词，而 T=2 摊开成三个
#          → 说明 temperature 生效了（排除乙）
#
#      任务 2（长，回答几十个字）—— 解释一句话
#          如果 T=0 下多次跑还是各不相同
#          → 说明短任务稳定、长任务不稳定，噪声被累积放大了
#
#  【已知局限，必须知道】
#      任务 1 的 prompt 里写了"随机选一个"，这等于命令模型把概率压平。
#      分布本来就扁平，T=0 没有明显的第一名可收敛，T=2 也没有空间可摊开。
#      所以任务 1 其实区分不出甲和乙——这是上一轮实测发现的。
#      这个脚本保留原样，是为了让你看到"没有区分度的实验"长什么样。
#      （正确的对照组应该用一个模型有明确偏好的题目，见笔记）
#
#  怎么跑：
#      先 cd 到本文件所在目录，然后执行
#          python stage0_c_temperature_effect.py
#
#      每次调用都会打印一行，看到它在动就说明正常。
#      中途想停按 Ctrl+C。
#
# ============================================================


# ------------------------------------------------------------
# 第一步：搬工具箱
# ------------------------------------------------------------
import os
import json
import time
from openai import OpenAI


# ------------------------------------------------------------
# 第二步：参数设置（嫌慢就把 N_SHORT / N_LONG 改小）
# ------------------------------------------------------------
BASE_URL = "https://api.deepseek.com"
MODEL = "deepseek-flash"

TEMPS = [0.0, 1.0, 2.0]     # 要对比的几个温度
N_SHORT = 30                # 任务 1：每个温度跑几次
N_LONG = 15                 # 任务 2：每个温度跑几次

SHORT_PROMPT = "从「苹果」「香蕉」「橘子」这三个词里随机选一个。只回答那个词，不要任何解释。"
LONG_PROMPT = "用一句话解释什么是数据库索引。"
# ------------------------------------------------------------


# ------------------------------------------------------------
# 第三步：路径和 API key（和脚本 A 一样）
# ------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
NOTES_DIR = os.path.join(HERE, "notes")

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
    print('  2. 在本目录建一个 myKey.txt，里面只写 key 本身')
    raise SystemExit

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)


# ------------------------------------------------------------
# 第四步：问一次模型
# ------------------------------------------------------------
def ask_once(prompt, temperature):
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=512,
    )
    text = resp.choices[0].message.content.strip()
    return text


# ------------------------------------------------------------
# 第五步：两个小工具
# ------------------------------------------------------------
def which_fruit(text):
    """从回答里认出是哪个水果。认不出就返回原文前 6 个字。"""
    fruits = ["苹果", "香蕉", "橘子"]
    for fruit in fruits:
        if fruit in text:
            return fruit
    if len(text) == 0:
        return "(空回答)"
    return text[:6]


def count_kinds(items):
    """数一数每个东西出现了几次，返回 {东西: 次数}"""
    counts = {}
    for one in items:
        if one in counts:
            counts[one] = counts[one] + 1
        else:
            counts[one] = 1
    return counts


# ------------------------------------------------------------
# 第六步：连通性自检 —— 先让你知道"它在动"
# ------------------------------------------------------------
# 上一轮这个脚本跑了 4 分钟屏幕上一个字都没刷，
# 看起来像卡死。所以这次先发一次请求，把耗时告诉用户。
print("正在测试连接 ...")
probe_start = time.time()
ask_once("回复一个字：好", 0.0)
probe_seconds = time.time() - probe_start

print("  连接正常，单次约 " + str(round(probe_seconds, 2)) + " 秒")

total_calls = len(TEMPS) * (N_SHORT + N_LONG)
estimated_minutes = total_calls * probe_seconds / 60
print("  总共 " + str(total_calls) + " 次调用，预计 "
      + str(round(estimated_minutes, 1)) + " 分钟")
print("  每次调用都会打印一行，看到它在动就说明一切正常。")
print("")


# ------------------------------------------------------------
# 第七步：任务 1 —— 短输出，从三个词里选一个
# ------------------------------------------------------------
print("=" * 60)
print("  任务 1 · 短输出：从三个词里选一个")
print("=" * 60)
print("  问题：" + SHORT_PROMPT)
print("  每个温度跑 " + str(N_SHORT) + " 次")
print("")

short_result = {}     # {温度: {水果: 次数}}

for t in TEMPS:
    print("  --- temperature = " + str(t) + " ---")

    picks = []
    start_time = time.time()

    for i in range(N_SHORT):
        text = ask_once(SHORT_PROMPT, t)
        fruit = which_fruit(text)
        picks.append(fruit)
        print("    [" + str(i + 1).rjust(2) + "/" + str(N_SHORT) + "]  " + fruit)

    counts = count_kinds(picks)
    short_result[str(t)] = counts

    used = time.time() - start_time
    print("    → 用时 " + str(round(used)) + " 秒，分布：")

    fruits = ["苹果", "香蕉", "橘子"]
    for fruit in fruits:
        if fruit in counts:
            n = counts[fruit]
        else:
            n = 0
        percent = round(n / N_SHORT * 100)
        bars = "#" * n
        print("       " + fruit + "  " + str(n).rjust(2) + " 次 ("
              + str(percent).rjust(3) + "%)  " + bars)

    print("")


# ------------------------------------------------------------
# 第八步：任务 2 —— 长输出，解释一句话
# ------------------------------------------------------------
print("=" * 60)
print("  任务 2 · 长输出：用一句话解释数据库索引")
print("=" * 60)
print("  每个温度跑 " + str(N_LONG) + " 次，数有几种不同的回答")
print("")

long_result = {}      # {温度: [回答列表]}

for t in TEMPS:
    print("  --- temperature = " + str(t) + " ---")

    answers = []
    start_time = time.time()

    for i in range(N_LONG):
        text = ask_once(LONG_PROMPT, t)
        answers.append(text)
        print("    [" + str(i + 1).rjust(2) + "/" + str(N_LONG) + "]  " + text[:44])

    distinct = len(count_kinds(answers))

    total_chars = 0
    for a in answers:
        total_chars = total_chars + len(a)
    average_chars = round(total_chars / len(answers))

    long_result[str(t)] = answers

    used = time.time() - start_time
    print("    → 用时 " + str(round(used)) + " 秒，"
          + str(N_LONG) + " 次出现 " + str(distinct) + " 种不同回答"
          + "（平均 " + str(average_chars) + " 字）")
    print("")


# ------------------------------------------------------------
# 第九步：结论
# ------------------------------------------------------------
print("#" * 60)
print("#  怎么读这两个结果")
print("#" * 60)

# 任务 1：T=0 时最常见的那个水果占多少
t0_counts = short_result.get("0.0", {})
t0_top_percent = 0.0
if len(t0_counts) > 0:
    biggest = 0
    for fruit in t0_counts:
        if t0_counts[fruit] > biggest:
            biggest = t0_counts[fruit]
    t0_top_percent = biggest / N_SHORT

t2_counts = short_result.get("2.0", {})
t2_kinds = len(t2_counts)

print("")
print("  任务 1（短输出）：")
print("    T=0 时，最常见的那个词占了 " + str(round(t0_top_percent * 100)) + "%")
print("    T=2 时，出现了 " + str(t2_kinds) + " 种不同的词")
print("")

if t0_top_percent >= 0.9 and t2_kinds >= 2:
    print("    ⇒ temperature 生效了：T=0 高度集中，T=2 摊开了。")
else:
    print("    ⇒ T=0 没有收敛，区分不出「temperature 生效」还是「被忽略」。")
    print("       原因：prompt 要求「随机选一个」，把概率压平了，")
    print("       上下都没有区分度 —— 这是个失败的控制组，记住它。")

# 任务 2：T=0 时有多少种不同回答
t0_long = long_result.get("0.0", [])
t0_distinct = len(count_kinds(t0_long))

print("")
print("  任务 2（长输出）：")
print("    T=0 时，" + str(N_LONG) + " 次里出现了 " + str(t0_distinct) + " 种不同回答")
print("")

if t0_distinct > N_LONG * 0.5:
    print("    ⇒ T=0 在长输出上完全不可复现。")
    print("       结合脚本 A 和这次的短任务结果，可以确认：")
    print("       【结论】T=0 提高可复现性，但不保证可复现。")
    print("       原因推断：服务端存在每个 token 都有的微小非确定性，")
    print("                 经过几十个 token 的生成被累积放大。")
elif t0_distinct <= 1:
    print("    ⇒ T=0 在长任务上也完全稳定，那脚本 A 的结果要重新解释。")

print("")
print("  对 eval 的意义：")
print("    即使 temperature 设成 0，重跑一次评测分数仍可能不同。")
print("    「噪声地板」这件事绕不过去。")


# ------------------------------------------------------------
# 第十步：存盘
# ------------------------------------------------------------
os.makedirs(NOTES_DIR, exist_ok=True)

data = {
    "model": MODEL,
    "temps": TEMPS,
    "n_short": N_SHORT,
    "n_long": N_LONG,
    "short_distribution": short_result,
    "long_answers": long_result,
}

json_path = os.path.join(NOTES_DIR, "stage0_c_raw.json")
f = open(json_path, "w", encoding="utf-8")
json.dump(data, f, ensure_ascii=False, indent=2)
f.close()

print("")
print("  原始数据 → " + json_path)
print("-" * 60)
