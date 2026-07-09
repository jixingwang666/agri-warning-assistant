# 文本分析模块

本模块负责农业新闻的分词、停用词过滤、关键词提取、摘要生成和新闻分类。

## 目录结构

```text
text_analysis/
├─ __init__.py
├─ analyzer.py
├─ classifier.py
├─ keywords.py
├─ ml_classifier.py
├─ run_analysis.py
├─ summarizer.py
├─ tokenizer.py
├─ resources/
│  ├─ agriculture_keywords.txt
│  ├─ labeled_news.csv
│  └─ stopwords.txt
└─ output/
   └─ analyzed_news.csv
```

## 运行方式

在项目根目录执行：

```bash
D:\Develop\Tools\agri-warning-venv\Scripts\python.exe project\text_analysis\run_analysis.py
```

运行后会读取第一模块中的演示新闻：

```text
project/data_collection/sample_data/sample_news.csv
```

并输出分析结果到：

```text
project/text_analysis/output/analyzed_news.csv
```

## 输出字段

| 字段 | 说明 |
| --- | --- |
| title | 新闻标题 |
| source | 新闻来源 |
| publish_time | 发布时间 |
| url | 新闻链接 |
| region | 地区 |
| category | 自动分类 |
| summary | 自动摘要 |
| keywords | 关键词 |

## 说明

当前版本以稳定可运行为主：

- 分词优先使用 `jieba`
- 关键词提取使用 TF-IDF 思路
- 摘要使用句子打分的抽取式摘要
- 分类使用农业领域关键词规则
- `ml_classifier.py` 提供机器学习分类样例接口

## 分类器对比

如需对比规则分类和机器学习分类，可执行：

```bash
D:\Develop\Tools\agri-warning-venv\Scripts\python.exe project\text_analysis\run_classifier_compare.py
```

结果会保存到：

```text
project/text_analysis/output/classifier_compare.csv
```

## 本地模型优化（真实新闻重训 + 推理门控）

背景：本地模型只在 AgriCHN 短句上训练，迁移到真实全文新闻时准确率骤降
（真实新闻 40% < 规则 73%，见 `test_results/test_2_model.md`）。优化分两部分。

### 1. 推理门控（已生效，无需重训）

`classifier.py` 的离线分类链路由「模型优先」改为 **规则优先 → 模型兜底 → 其他**
（`classify_news_offline`）：

- 真实新闻文章关键词密集，规则更可靠，命中即返回，避免模型「农业政策」高置信误判。
- AgriCHN 式短文本关键词稀疏、规则弃权时，才用本地模型兜底。
- OOD 输入（纯英文/符号/空，`inference.is_ood`）跳过模型。
- `inference.py` 对模型输入做**标题加权**（标题前置重复），贴近训练分布。

评估对比：

```bash
python text_analysis/run_gating_eval.py
```

实测：真实新闻 40%/50% → **100%**，AgriCHN 短文本仍约 **60%**（取长补短）。

### 2. 真实新闻重训（数据积累到位后执行）

用 LLM(DeepSeek) 自动标注反向爬虫产出的真实新闻，混入 AgriCHN 重训：

```bash
# a) 反向爬虫先产出真实新闻 CSV（见 data_collection/run_search_crawler_check.py）
# b) 用 DeepSeek 自动标注 -> training_data/realnews_single.json（需开启 LLM）
python text_analysis/build_realnews_dataset.py
# c) 重训（自动混入 realnews_single.json，真实样本按 x5 过采样）
python text_analysis/train_classifier.py
# d) 复评
python text_analysis/run_gating_eval.py
```

说明：真实标注样本越多，重训对分布不匹配的修复越明显；建议持续多轮爬取+标注
积累到数百条以上再重训。`build_realnews_dataset.py` 只保留置信度 ≥ 0.8 且属于
6 个类别的样本，并按文本去重、增量追加。
