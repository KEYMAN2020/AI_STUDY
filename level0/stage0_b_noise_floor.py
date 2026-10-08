# ============================================================
#  level0 · 脚本 B —— 测出你的"噪声地板"   ★ level0 的核心
# ============================================================
#
#  这个脚本做什么：
#      出一套有标准答案的算术题，整套连跑 5 遍。
#      然后算出两个"分数会晃多少"的数字：
#
#        采样抖动   —— 同一套题、同一份代码，连跑 5 遍得到的 5 个分数
#                      因为 temperature 不是 0，每次答得不一样
#
#        数据集抖动 —— 从这套题里随机抽一部分算分，重复很多次
#                      因为题太少，抽到哪些题会影响分数
#
#  你会看到：
#      你什么都没改，分数却在晃。那个晃动幅度就是你的"噪声地板"。
#      它决定了：多大的改进，你才有资格说"这真的有效果"。
#
#  为什么要用算术题：
#      对错可以用"正确答案在不在回答里"直接判断，
#      不需要裁判模型，也不需要任何评测框架。
#      这一步的目的不是测模型，是让你亲眼看到"分数会晃"。
#
#  怎么跑：
#      先 cd 到本文件所在目录，然后执行
#          python stage0_b_noise_floor.py
#
# ============================================================


# ------------------------------------------------------------
# 第一步：搬工具箱
# ------------------------------------------------------------
import os       # 路径、环境变量、文件夹
import json     # 把结果存成 json
import random   # 出题、随机抽样
from openai import OpenAI


# ------------------------------------------------------------
# 第二步：参数设置（嫌跑得慢就改小 N_RUNS 和 N_ROUNDS）
# ------------------------------------------------------------
BASE_URL = "https://api.deepseek.com"
MODEL = "deepseek-flash"

N_QUESTIONS = 30    # 一共出几道题
N_RUNS = 5          # 整套连跑几遍（用来测采样抖动）
N_SUB = 15          # 数据集抖动：每次抽几道题
N_ROUNDS = 20       # 数据集抖动：重复抽几次
DIGITS = 4          # 乘数有几位数。越大越难
                    # 实测：3 位数模型 5 遍全对，没有区分度，所以用 4 位数
SEED = 42           # 随机种子。固定住它，每次跑的题目和抽样才一样
# ------------------------------------------------------------


# ------------------------------------------------------------
# 第三步：路径和 API key（跟脚本 A 一样，不再重复解释）
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

print("使用 key ：", API_KEY[:6] + "...")
print("使用模型 ：", MODEL)

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)


# ------------------------------------------------------------
# 第四步：出题
# ------------------------------------------------------------
random.seed(SEED)      # 固定随机种子，保证每次生成同样的题目

# 4 位数的话，最小是 1000，最大是 9999
smallest = 10 ** (DIGITS - 1)
largest = 10 ** DIGITS - 1

questions = []         # 每道题是一个字典：题目文字 + 标准答案

for i in range(N_QUESTIONS):
    a = random.randint(smallest, largest)
    b = random.randint(smallest, largest)

    prompt = "计算 " + str(a) + " × " + str(b) + " 等于多少？只回答一个数字，不要任何其他文字。"
    expected = str(a * b)      # 标准答案，转成文字方便比对

    questions.append({"prompt": prompt, "expected": expected})

print("")
print("已生成 " + str(N_QUESTIONS) + " 道题（" + str(DIGITS) + " 位数乘法）")
print("整套连跑 " + str(N_RUNS) + " 遍，共 " + str(N_QUESTIONS * N_RUNS) + " 次调用")


# ------------------------------------------------------------
# 第五步：问一次模型
# ------------------------------------------------------------
def ask_once(prompt):
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=1,      # 这里特意用 1，保留随机性——这正是我们要测的东西
        max_tokens=512,     # 防止回答被截断
    )
    text = resp.choices[0].message.content.strip()
    return text


# ------------------------------------------------------------
# 第六步：判断这一题答对没有
# ------------------------------------------------------------
def is_correct(answer, expected):
    # 模型可能写成 "1,234,567" 这种带千分位逗号的形式，
    # 所以先把逗号去掉再比对。
    cleaned = answer.replace(",", "").replace("，", "")

    # 只要标准答案出现在回答里，就算对
    if expected in cleaned:
        return True
    else:
        return False


# ------------------------------------------------------------
# 第七步：整套题跑一遍
# ------------------------------------------------------------
def run_one_pass(pass_number):
    print("")
    print("=" * 60)
    print("  第 " + str(pass_number) + " / " + str(N_RUNS) + " 遍")
    print("=" * 60)

    results = []          # 每题的得分：答对记 1，答错记 0
    correct_count = 0     # 这一遍答对了几题

    for i in range(N_QUESTIONS):
        q = questions[i]
        answer = ask_once(q["prompt"])
        ok = is_correct(answer, q["expected"])

        if ok:
            results.append(1)
            correct_count = correct_count + 1
            mark = "对"
        else:
            results.append(0)
            mark = "错"

        print("  [" + str(i + 1).rjust(2) + "/" + str(N_QUESTIONS) + "]"
              + "  正确 " + q["expected"].rjust(8)
              + "   模型答 " + answer[:18].ljust(20)
              + "  " + mark)

    score = correct_count / N_QUESTIONS
    print("  → 这一遍得分：" + str(round(score * 100, 1)) + "%")

    return results, score


# ------------------------------------------------------------
# 第八步：整套连跑 N_RUNS 遍，收集所有分数
# ------------------------------------------------------------
all_results = []     # 每一遍的得分明细（一串 0 和 1）
all_scores = []      # 每一遍的总分

for run in range(1, N_RUNS + 1):
    this_results, this_score = run_one_pass(run)
    all_results.append(this_results)
    all_scores.append(this_score)


# ------------------------------------------------------------
# 第九步：算"采样抖动"
# ------------------------------------------------------------
highest = max(all_scores)
lowest = min(all_scores)
sampling_noise = (highest - lowest) / 2

print("")
print("=" * 60)
print("  采样抖动")
print("=" * 60)

for i in range(len(all_scores)):
    bars = "#" * round(all_scores[i] * 40)
    print("    第 " + str(i + 1) + " 遍："
          + str(round(all_scores[i] * 100, 1)).rjust(5) + "%  " + bars)

print("")
print("    最高 " + str(round(highest * 100, 1)) + "%"
      + "   最低 " + str(round(lowest * 100, 1)) + "%"
      + "   差 " + str(round((highest - lowest) * 100, 1)) + "%")
print("    → 采样抖动 ≈ ±" + str(round(sampling_noise * 100, 1)) + "%")
print("      （同一套题、同一份代码，什么都没改，分数就差了这么多）")


# ------------------------------------------------------------
# 第十步：先检查"这套题有没有区分度"
# ------------------------------------------------------------
# 如果模型全对或全错，那分数永远是 100% 或 0%，
# 测出来的抖动是 0 —— 但这个 0 不代表"系统很稳"，
# 它只代表"这把尺子没有刻度"。
average = sum(all_scores) / len(all_scores)
no_discrimination = False

if average == 1.0:
    no_discrimination = True
    print("")
    print("!" * 60)
    print("  模型全对了 —— 这套题太简单，测不出任何抖动。")
    print("  一个所有人都考 100 分的测试，是没有区分度的。")
    print("  请把脚本顶部的 DIGITS 从 " + str(DIGITS)
          + " 改成 " + str(DIGITS + 1) + "，再跑一次。")
    print("!" * 60)

if average == 0.0:
    no_discrimination = True
    print("")
    print("!" * 60)
    print("  模型全错了 —— 这套题太难，也测不出抖动。")
    print("  请把脚本顶部的 DIGITS 从 " + str(DIGITS)
          + " 改成 " + str(DIGITS - 1) + "，再跑一次。")
    print("!" * 60)


# ------------------------------------------------------------
# 第十一步：算"数据集抖动"
# ------------------------------------------------------------
# 拿第一遍的得分明细（一串固定的 0 和 1），
# 从中随机抽出 N_SUB 道，算一个分数。重复 N_ROUNDS 次。
base = all_results[0]

print("")
print("=" * 60)
print("  数据集抖动")
print("=" * 60)
print("  从这 " + str(N_QUESTIONS) + " 道里随机抽 " + str(N_SUB)
      + " 道算分，重复 " + str(N_ROUNDS) + " 次：")
print("")

sub_scores = []

for i in range(N_ROUNDS):
    sample = random.sample(base, N_SUB)      # 随机抽 N_SUB 个，不放回
    total = 0
    for one in sample:
        total = total + one
    score = total / N_SUB
    sub_scores.append(score)

    bars = "#" * round(score * 40)
    print("    第 " + str(i + 1).rjust(2) + " 次："
          + str(round(score * 100, 1)).rjust(5) + "%  " + bars)

sub_highest = max(sub_scores)
sub_lowest = min(sub_scores)
dataset_noise = (sub_highest - sub_lowest) / 2

print("")
print("    最高 " + str(round(sub_highest * 100, 1)) + "%"
      + "   最低 " + str(round(sub_lowest * 100, 1)) + "%"
      + "   差 " + str(round((sub_highest - sub_lowest) * 100, 1)) + "%")
print("    → 数据集抖动 ≈ ±" + str(round(dataset_noise * 100, 1)) + "%")
print("      （同一份输出，什么都没改，只是因为抽了不同的题）")

# 顺便算一个"全量分数的粗略置信区间"，让你看到"题少 = 不准"
if average > 0 and average < 1:
    # 这条公式先不用管原理，只要知道：题越少，这个区间越宽
    standard_error = (average * (1 - average) / N_QUESTIONS) ** 0.5
    margin = 1.96 * standard_error
    print("")
    print("    参考：全 " + str(N_QUESTIONS) + " 题得 "
          + str(round(average * 100, 1)) + "%，"
          + "95% 置信区间约 ±" + str(round(margin * 100, 1)) + "%")
    print("          意思是：真实水平大概在 "
          + str(round((average - margin) * 100)) + "% ~ "
          + str(round((average + margin) * 100)) + "% 之间")
    print("          想让这个区间缩一半，题目数量要变成 4 倍（约 "
          + str(N_QUESTIONS * 4) + " 题）")


# ------------------------------------------------------------
# 第十二步：汇总结论
# ------------------------------------------------------------
# 两个抖动互相独立。严格合并应该用平方和开根，
# 这里取较大的那个，更保守、也更好记。
if sampling_noise > dataset_noise:
    noise_floor = sampling_noise
else:
    noise_floor = dataset_noise

print("")
print("#" * 60)
print("#  你的噪声地板")
print("#" * 60)
print("  采样抖动      ±" + str(round(sampling_noise * 100, 1)) + "%")
print("  数据集抖动    ±" + str(round(dataset_noise * 100, 1)) + "%")
print("  --------------------------------")
print("  噪声地板      ±" + str(round(noise_floor * 100, 1)) + "%   （取两者较大的）")
print("")
print("  ⇒ 小于 ±" + str(round(noise_floor * 100, 1))
      + "% 的改进，用现在这套评测是测不出来的。")
print("     那不是「没改进」，是「你现在的尺子量不出来」。")


# ------------------------------------------------------------
# 第十三步：把结论写进 notes 文件夹
# ------------------------------------------------------------
os.makedirs(NOTES_DIR, exist_ok=True)

# 先准备"警告文字"。没有区分度时，这个警告必须写进文件本身，
# 否则文件里只留一个 ±0.0%，看起来像"噪声为零"，会误导以后回看的自己。
if no_discrimination:
    if average == 1.0:
        hint_digits = DIGITS + 1
        which = "全对"
    else:
        hint_digits = DIGITS - 1
        which = "全错"

    warning = ("> 警告：本次结果无效 —— 模型在这 " + str(N_QUESTIONS)
               + " 道题上" + which + "，这套题没有区分度。\n"
               + "> 测出来的 ±0.0% 不是「噪声为零」，而是「尺子没有刻度」。\n"
               + "> 请把脚本顶部的 DIGITS 改成 " + str(hint_digits) + " 后重跑。\n\n")
else:
    warning = ""

lines = []
lines.append(warning + "# 我的噪声地板（level0 产出物）")
lines.append("")
lines.append("模型 `" + MODEL + "`，题目 " + str(N_QUESTIONS) + " 道 "
             + str(DIGITS) + " 位数乘法，整套连跑 " + str(N_RUNS) + " 遍，")
lines.append("抽样 " + str(N_SUB) + "/" + str(N_QUESTIONS) + " × "
             + str(N_ROUNDS) + " 次。")
lines.append("")
lines.append("## 测出来的数")
lines.append("")
lines.append("| 项目 | 数值 |")
lines.append("|---|---|")
lines.append("| 采样抖动 | **±" + str(round(sampling_noise * 100, 1)) + "%** |")
lines.append("| 数据集抖动 | **±" + str(round(dataset_noise * 100, 1)) + "%** |")
lines.append("| 全量得分 | " + str(round(average * 100, 1)) + "% |")
lines.append("")
lines.append("## 四句话")
lines.append("")
lines.append("```")
lines.append("我的采样抖动      是 ±" + str(round(sampling_noise * 100, 1)) + "%")
lines.append("我的数据集抖动    是 ±" + str(round(dataset_noise * 100, 1)) + "%")
lines.append("跑一次 eval 要     ___ 分钟 / ___ 元    ← 自己填：token 数 × 定价页单价")
lines.append("结论：小于 ±" + str(round(noise_floor * 100, 1))
             + "% 的改进，用我现在的 eval 是测不出来的")
lines.append("```")
lines.append("")
lines.append("## 我以为会怎样 vs 实际怎样")
lines.append("")
lines.append("（自己写两三句）")
lines.append("")
lines.append("## 这件事改变了什么")
lines.append("")
lines.append("（自己写。比如：以后别人跟我说涨了 X%，我第一个要问的是……）")
lines.append("")

md_path = os.path.join(NOTES_DIR, "00-noise-floor.md")
f = open(md_path, "w", encoding="utf-8")
f.write("\n".join(lines))
f.close()


# ------------------------------------------------------------
# 第十四步：把原始数据存下来
# ------------------------------------------------------------
data = {
    "model": MODEL,
    "questions": [q["prompt"] for q in questions],
    "run_scores": all_scores,
    "run_details": all_results,
    "subsample_scores": sub_scores,
    "sampling_noise": sampling_noise,
    "dataset_noise": dataset_noise,
    "noise_floor": noise_floor,
}

json_path = os.path.join(NOTES_DIR, "stage0_b_raw.json")
f = open(json_path, "w", encoding="utf-8")
json.dump(data, f, ensure_ascii=False, indent=2)
f.close()

print("")
print("  原始数据 → " + json_path)
print("  产出物   → " + md_path)
print("")
print("  打开 00-noise-floor.md，把「跑一次 eval 要 ___ 元」填上，")
print("  再写两句「我以为会怎样 vs 实际怎样」。")
print("-" * 60)
