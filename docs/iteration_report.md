# 农业预警助手 — 迭代开发报告

**项目地址**: `c:\Users\a\Desktop\midschool\agri-warning-assistant`

**原始项目**: https://github.com/jixingwang666/agri-warning-assistant

**开发周期**: 2026-07-04

---

## 目录

1. [项目概述](#1-项目概述)
2. [迭代 1：项目拉取与架构解析](#2-迭代-1项目拉取与架构解析)
3. [迭代 2：LLM 接入 + 本地模型训练](#3-迭代-2llm-接入--本地模型训练)
4. [迭代 3：综合测试](#4-迭代-3综合测试)
5. [迭代 4：架构优化 — 双模式切换](#5-迭代-4架构优化--双模式切换)
6. [当前架构总览](#6-当前架构总览)
7. [待办问题清单](#7-待办问题清单)
8. [文件改动清单](#8-文件改动清单)

---

## 1. 项目概述

### 原始项目

一个基于 Python 的**农业新闻舆情与风险预警系统**，技术栈：

| 层 | 技术 |
|----|------|
| 数据采集 | `requests` + `BeautifulSoup` 爬虫，CSV/Excel 导入 |
| 文本分析 | `jieba` 分词，TF-IDF 关键词，抽取式摘要，关键词规则分类 |
| 风险预警 | 关键词匹配评分公式，静态建议模板 |
| 数据管理 | FastAPI + MySQL，16 个 REST 接口 |
| 前端 | Vue 3 (CDN) + Element Plus + ECharts，零构建 |

### 原始项目的核心问题

1. **分类纯靠关键词匹配** — `str.count()` 子串匹配，无否定句处理、无语义理解
2. **建议纯靠静态模板** — 6 条硬编码文本，无论什么新闻都输出相同建议
3. **零测试覆盖** — 没有任何测试文件

### 改造目标

将纯规则系统改造为 **LLM + 本地模型** 驱动的智能预警系统。

---

## 2. 迭代 1：项目拉取与架构解析

**时间**: 2026-07-04 上午

### 工作内容

1. 从 GitHub 克隆项目到本地
2. 完整解析 5 个模块的 30+ 个源文件
3. 梳理数据流向和模块间依赖关系

### 原始架构

```
data_collection/     → 爬虫获取新闻 + CSV导入
       ↓
text_analysis/       → 分词 → 关键词提取 → 摘要 → 关键词规则分类
       ↓
risk_warning/        → 关键词评分 → 静态模板建议 → CSV输出
       ↓
data_management/     → MySQL存储 → FastAPI接口
       ↓
frontend/            → Vue 3 Web界面展示
```

### 关键发现

- 分类器：`classifier.py` 中 `classify_news()` 使用 6 组关键词做纯 `str.count()` 匹配
- 评分器：`scorer.py` 中 `score_news_item()` 使用 `keyword + price + heat + region - positive` 公式
- 建议模板：`risk_rules.py` 中 `SUGGESTION_TEMPLATES` 为 6 条固定文本
- 可选的 ML 分类器：`ml_classifier.py` 仅含 sklearn LogisticRegression，6 条训练样本

---

## 3. 迭代 2：LLM 接入 + 本地模型训练

**时间**: 2026-07-04 中午

### 3.1 需求

1. 接入 DeepSeek 大模型，替换静态建议模板
2. 增加 LLM 分类能力，替代关键词匹配
3. 训练本地轻量模型，作为离线后备

### 3.2 实施内容

#### 3.2.1 LLM 基础设施

| 文件 | 操作 | 说明 |
|------|------|------|
| `data_management/config.py` | 修改 | 新增 `LLMConfig` dataclass，7 个配置字段 |
| `data_management/.env` | 修改 | 新增 `AGRI_LLM_*` 环境变量 |
| `data_management/secrets.env` | **新建** | 独立存储 API key，已加入 `.gitignore` |
| `.gitignore` | **新建** | 排除 secrets、模型文件、临时文件 |

**LLM 配置**:
```
Provider:     DeepSeek (api.deepseek.com)
Model:        deepseek-chat
SDK:          openai (优先) → requests (降级)
Timeout:      30s
Temperature:  0.3
Max Tokens:   600
```

#### 3.2.2 LLM 预警增强

| 文件 | 操作 | 说明 |
|------|------|------|
| `risk_warning/llm_enricher.py` | **新建** | LLM 客户端 + 单条/批量增强函数（~150 行） |
| `risk_warning/risk_rules.py` | 修改 | 新增 4 个 LLM prompt 模板 |
| `risk_warning/warning_generator.py` | 修改 | `generate_warnings()` 增加 LLM 增强调用 |

**降级链路**（7 层）:
```
LLM disabled → API key 无效 → SDK 不可用 → 网络超时
→ 返回非 JSON → JSON 缺字段 → 批量数量错误
```
每层失败均回退到规则模板，保证系统可用。

#### 3.2.3 LLM 分类增强

| 文件 | 操作 | 说明 |
|------|------|------|
| `text_analysis/llm_classifier.py` | **新建** | LLM 新闻分类 + 风险类型检测（~80 行） |
| `text_analysis/classifier.py` | 修改 | 三级分类链：LLM → 本地模型 → 规则 |
| `risk_warning/scorer.py` | 修改 | 新增 `detect_risk_type_hybrid()`（LLM → 规则） |

#### 3.2.4 本地模型训练

| 文件 | 操作 | 说明 |
|------|------|------|
| `text_analysis/dataset_builder.py` | **新建** | AgriCHN-2023 BIO 标注 → 6 类分类数据集 |
| `text_analysis/train_classifier.py` | **新建** | BERT 微调训练脚本（GPU: RTX 4060） |
| `text_analysis/inference.py` | **新建** | BERT/TextCNN 双模型推理接口 |

**数据集**: AgriCHN-2023（GitHub 公开）
- 训练集: 3,897 条（单标签扩充后）
- 验证集: 475 条
- 测试集: 473 条
- 6 个类别: 农业政策、农业科技、农产品价格、市场供需、气象灾害、病虫害

**模型**: `bert-base-chinese` 微调
- 参数量: ~102M
- 模型大小: 391 MB
- 训练硬件: NVIDIA RTX 4060 Laptop (8GB VRAM)
- 训练耗时: ~7 分钟（10 epochs）
- 测试准确率: 61.3%（AgriCHN 测试集）

**TextCNN 对照实验**（后弃用）:
- 参数量: 770K
- 模型大小: 3 MB
- 测试准确率: 58.6%
- 弃用原因: 准确率低于 BERT，且低于关键词规则基线

---

## 4. 迭代 3：综合测试

**时间**: 2026-07-04 下午

### 4.1 测试策略

采用 **人机对比评测** 方法：人眼判断基准 → 系统分析 → 对比差异 → 记录结论。

测试 3 个核心组件，共 46 条用例。

### 4.2 测试 1：爬虫数据采集（12 条用例）

#### 测试设计

| 组 | 用例数 | 类型 | 测试内容 |
|----|--------|------|----------|
| A 组 | 5 | 离线 | CSV 导入、清洗、去重、链接过滤 |
| B 组 | 7 | 联网 | 真实爬取 moa.gov.cn + farmer.com.cn |

#### 测试数据

| 数据源 | 条数 | 说明 |
|--------|------|------|
| `sample_news.csv` | 5 条 | 项目自带演示数据 |
| `sample_prices.csv` | 6 条 | 项目自带价格数据 |
| 爬虫实时抓取 | 5 条 | farmer.com.cn 实时爬取 |
| 构造的重复/异常数据 | 5 条 | 用于去重和过滤测试 |

#### 测试结果

| 指标 | 结果 |
|------|------|
| 离线测试通过率 | **5/5 (100%)** |
| 联网测试通过率 | **6/7 (86%)** |
| farmer.com.cn | ✅ 5 条有效新闻 |
| moa.gov.cn | ❌ 0 条（CSS 选择器不匹配 → ISSUE-CR-001） |
| 有效新闻数 | 4/5（1 条为页脚链接噪声 → ISSUE-CR-002） |
| 中文内容率 | 100% |
| 爬取耗时 | 5.8 秒 |

### 4.3 测试 2：模型分类分析（16 条用例）

#### 测试设计

| 组 | 用例数 | 测试内容 |
|----|--------|----------|
| A 组 | 4 | 真实新闻人眼 vs 规则 vs 模型三方对比 |
| B 组 | 4 | 项目自带数据对比 |
| C 组 | 4 | AgriCHN 473 条批量评估 + 20 条人眼复核 |
| D 组 | 4 | 边界情况（空文本/超长/纯英文/纯符号） |

#### 测试数据

| 数据源 | 条数 | 用途 |
|--------|------|------|
| 爬取新闻 | 4 条有效 + 1 条噪声 | 真实场景测试 |
| `sample_news.csv` | 5 条 | 项目 demo 数据 |
| `labeled_news.csv` | 6 条 | 项目标注数据 |
| AgriCHN 测试集 | 473 条 | 批量准确率评估 |
| 边界手工用例 | 4 条 | 鲁棒性测试 |

#### 测试结果

**三方对比（16 条真实新闻 + 样本）**:

| 对比维度 | 一致数 | 一致率 | 判定 |
|----------|--------|--------|------|
| 模型 vs 人眼 | 6/15 | **40%** | ❌ 未达标 (< 60%) |
| 规则 vs 人眼 | 11/15 | **73%** | ✅ |
| 模型 vs 规则 | - | 落后 5 条 | ❌ |

**AgriCHN 测试集（473 条）**:

| 指标 | 模型 | 规则 |
|------|------|------|
| Overall Accuracy | **61.3%** | 11.0% |
| 病虫害 F1 | 68.8% | 26.4% |
| 农业政策 F1 | 97.4% | 0.0% |
| 气象灾害 F1 | 47.8% | 15.2% |

**关键发现**:
- 模型在短文本（AgriCHN）上优于规则（61.3% vs 11.0%）
- 规则在真实新闻上优于模型（73% vs 40%）
- 模型存在"农业政策"偏好——高置信度误判
- 训练数据分布不一致导致的泛化问题

**边界测试**: 5/5 不崩溃 ✅  
**确定性**: 同输入 5 次推理完全一致 ✅

### 4.4 测试 3：LLM 预警增强（18 条用例）

#### 测试设计

| 组 | 用例数 | 测试内容 |
|----|--------|----------|
| A 组 | 6 | 功能测试（单条/批量/低风险跳过/端到端） |
| B 组 | 4 | 人眼质量评估（4 维度 × 3 分制） |
| C 组 | 7 | 降级链路（7 种故障场景） |
| D 组 | 1 | 稳定性（同输入 3 次调用） |

#### 测试数据

| 数据 | 说明 |
|------|------|
| 病虫害预警 | 小麦赤霉病，河南，score=78 |
| 气象灾害预警 | 强降雨，河南，score=72 |
| 价格波动预警 | 蔬菜价格，郑州，score=45 |
| 低风险预警 | score=20（测试跳过逻辑） |
| Mock 故障场景 | 7 种模拟故障 |

#### 测试结果

**功能测试**: 6/6 全部通过 ✅

**质量评估（人眼 vs LLM vs 规则模板）**:

| 预警 | 具体性 | 可操作性 | 准确性 | 无幻觉 | 总分 |
|------|--------|----------|--------|--------|------|
| 病虫害 | 3/3 | 3/3 | 3/3 | 3/3 | **12/12** |
| 气象灾害 | 3/3 | 3/3 | 3/3 | 3/3 | **12/12** |
| 价格波动 | 3/3 | 2/3 | 3/3 | 3/3 | **11/12** |
| **平均** | **3.0** | **2.7** | **3.0** | **3.0** | **11.7/12** |

**LLM vs 规则模板对比**:

| 维度 | 规则模板 | LLM 输出 |
|------|----------|----------|
| 长度 | ~30 字 | 80-120 字 |
| 产品提及 | 无 | 有（小麦/蔬菜） |
| 地区提及 | 无 | 有（河南/郑州） |
| 具体措施 | "加强田间巡查" | "抽穗扬花期喷施戊唑醇" |
| 评分利用 | 无 | 分析各子分数含义 |

**降级测试**: 7/7 全部通过 ✅  
**稳定性**: 3/3 核心意思一致 ✅（temperature=0.3）

---

## 5. 迭代 4：架构优化 — 双模式切换

**时间**: 2026-07-04 傍晚

### 5.1 基于测试数据的决策

| 组件 | 真实新闻 | 短文本 | 成本 | 延迟 | 角色定位 |
|------|----------|--------|------|------|----------|
| LLM 分类 | ~85%+（预期） | 同 | ~¥0.007/次 | 2-5s | **联网首选** |
| 规则分类 | 73% | 11% | 免费 | <1ms | 移除独立层级 |
| 模型分类 | 40% | 61.3% | 免费 | ~100ms | **离线首选** |
| LLM 建议 | 11.7/12 | 同 | ~¥0.003/次 | 2-5s | **联网首选** |

### 5.2 最终架构

```
                 LLM_CONFIG.enabled?
                    /          \
                  YES           NO
                  /              \
           【联网模式】        【离线模式】
                 │                 │
          分类: DeepSeek      分类: BERT 模型
          建议: DeepSeek      建议: 规则模板
          风险: LLM hybrid    风险: 规则关键词
```

### 5.3 实施改动

| 文件 | 改动 | 说明 |
|------|------|------|
| `classifier.py` | 重写 `classify_news()` | LLM → 降级到模型 → 规则兜底 |
| `scorer.py` | 接入 `detect_risk_type_hybrid()` | 风险检测 LLM 优先 |

仅改动 **2 个文件的 2 个函数**。

---

## 6. 当前架构总览

### 数据流

```
新闻来源（爬虫/CSV导入）
       │
       ▼
  【分类】                     【风险检测】              【建议生成】
  LLM → 模型 → 规则           LLM → 规则                LLM → 模板
       │                         │                        │
       └─────────┬───────────────┘                        │
                 ▼                                        │
          【风险评分】                                     │
          公式: keyword+price+heat+region-positive         │
                 │                                        │
                 └────────────┬───────────────────────────┘
                              ▼
                       【预警输出】
                       MySQL → FastAPI → 前端
```

### 新增文件（9 个）

| 文件 | 模块 | 功能 |
|------|------|------|
| `risk_warning/llm_enricher.py` | 预警 | LLM 客户端 + 建议增强 |
| `text_analysis/llm_classifier.py` | 分类 | LLM 零样本分类 |
| `text_analysis/dataset_builder.py` | 训练 | AgriCHN → 分类数据集 |
| `text_analysis/train_classifier.py` | 训练 | BERT 微调训练 |
| `text_analysis/inference.py` | 推理 | 模型推理接口 |
| `data_management/secrets.env` | 配置 | API key 独立存储 |
| `.gitignore` | 配置 | 安全排除 |
| `docs/iteration_report.md` | 文档 | 本报告 |
| `test_results/` (4 文件) | 测试 | 测试结果文档 |

### 修改文件（6 个）

| 文件 | 改动 |
|------|------|
| `data_management/config.py` | 新增 `LLMConfig` |
| `data_management/.env` | 新增 LLM 配置项 |
| `risk_warning/risk_rules.py` | 新增 4 个 prompt 模板 |
| `risk_warning/warning_generator.py` | 集成 LLM 增强 |
| `text_analysis/classifier.py` | 双模式分类链 |
| `risk_warning/scorer.py` | 接入混合风险检测 |

---

## 7. 待办问题清单

| 编号 | 严重性 | 类别 | 描述 |
|------|--------|------|------|
| ISSUE-CR-001 | 中 | 爬虫 | moa.gov.cn 返回 0 条，CSS 选择器需更新 |
| ISSUE-CR-002 | 中 | 爬虫 | 页脚链接穿透关键词过滤 |
| ISSUE-CR-003 | 低 | 爬虫 | 中文源编码声明不准确 |
| ISSUE-MD-001 | 高 | 模型 | 模型在真实新闻上准确率仅 40%，训练/推理数据分布不一致 |
| ISSUE-MD-002 | 中 | 模型 | 模型存在"农业政策"偏好，高置信度误判 |
| ISSUE-MD-003 | 中 | 模型 | OOD 输入置信度异常高 |
| ISSUE-MD-004 | 低 | 模型 | AgriCHN 部分标签存疑 |
| ISSUE-LL-001 | 低 | LLM | 批量 prompt 与单条 prompt 结构不同 |
| ISSUE-LL-002 | 低 | LLM | JSON 解析正则不支持嵌套 |

---

## 8. 文件改动清单

```
agri-warning-assistant/
├── .gitignore                              [新建] Git 安全排除
├── docs/
│   └── iteration_report.md                 [新建] 本报告
├── test_results/
│   ├── test_1_crawler.md                   [新建] 爬虫测试
│   ├── test_2_model.md                     [新建] 模型测试
│   ├── test_3_llm.md                       [新建] LLM 测试
│   └── test_summary.md                     [新建] 测试总结
├── data_management/
│   ├── .env                                [修改] +LLM 配置
│   ├── config.py                           [修改] +LLMConfig
│   └── secrets.env                         [新建] API key
├── risk_warning/
│   ├── llm_enricher.py                     [新建] LLM 增强
│   ├── risk_rules.py                       [修改] +prompt 模板
│   ├── scorer.py                           [修改] +hybrid 检测
│   └── warning_generator.py                [修改] +LLM 集成
└── text_analysis/
    ├── classifier.py                       [修改] 双模式分类
    ├── llm_classifier.py                   [新建] LLM 分类
    ├── dataset_builder.py                  [新建] 数据集构造
    ├── train_classifier.py                 [新建] BERT 训练
    ├── inference.py                        [新建] 模型推理
    ├── models/                             [新建] 训练产物
    ├── training_data/                      [新建] 训练数据
    └── agrichn_dataset/                    [新建] 原始数据集
```
