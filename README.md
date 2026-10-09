# 文小星

使用 Streamlit 构建的梅花易数时间起卦网页。Python 负责排盘，DeepSeek 仅解读已经生成的卦象，不重新起卦。

## 功能

- 按北京时间选择公历日期、小时区间，填写问题和可选背景。
- 展示本卦、互卦、变卦、动爻和体用关系。
- 基于固定结构的 JSON 调用 DeepSeek，并校验回复。
- 页面解读分为总断、卦象大意、分析、应期、建议；内部保留完整的十一节解读及依据。
- 解读失败时保留排盘，可单独重试模型请求。
- 没有候选公司名单时，只分析公司画像和筛选标准，不编造公司名称。

## 本地运行

需要 Python 3.12 或更新版本。Windows 可双击 `start.cmd`；首次运行会准备环境并安装依赖，需要联网。保留运行窗口，关闭服务时按 Ctrl+C。

Windows 也可以手动启动：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Linux：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py
```

浏览器打开 `http://127.0.0.1:8501`。配置默认只监听本机地址。

## DeepSeek 配置

复制 `.streamlit/secrets.example.toml` 为 `.streamlit/secrets.toml`，填写自己的密钥：

```toml
[deepseek]
api_key = "填写自己的 DeepSeek API Key"
model = "deepseek-chat"
```

也支持环境变量 `DEEPSEEK_API_KEY`；本地文件中非空的密钥优先。页面不提供 API Key 输入框。

实际密钥文件已加入 `.gitignore`，不要提交到仓库。仓库只保留空白示例。模型请求会把本次问题、背景及排盘数据发送至 DeepSeek；仅编辑输入字段不会重复发送请求。

## 排盘与解读

输入按北京时间解释。网页向库传入 `datetime(year, month, day, hour, 0, 0)`，不自行转换农历或重新计算起卦。只支持 1900 年 1 月 31 日至 2099 年 12 月 31 日的公历日期；农历依赖缺失时拒绝排盘。

沿用库规则：23 点属子时但不提前换日，闰月沿用月号，不进行真太阳时校正。小时采用 24 小时制，03 表示凌晨 3 点，15 表示下午 3 点。

提示词位于 `prompts/reading_system.txt`。内部顺序为读卦复核、总断、体用生克、卦名与卦象、动爻爻辞、互卦看过程、变卦看结果、结合用户问题、应期、建议、局限声明。展示层将其合并为五类，隐藏复核、局限声明章节及依据标注，保留其余正文。

当前库不包含完整卦辞、爻辞资料，`gua_ci` 与 `yao_ci` 明确传入 `null`，模型不得补写未提供的引文。问题屏蔽和输出校验采用词语及结构规则，不能保证识别所有语义错误。解读仅供文化参考与决策辅助，不是事实保证。

## 检查

Windows：

```powershell
.\.venv\Scripts\python.exe run_checks.py
```

Linux：

```bash
.venv/bin/python run_checks.py
```

检查覆盖起卦案例、日期与时间契约、农历缺失处理、模型错误、输出校验、展示内容保留和页面交互。模型检查使用模拟服务，不消耗实际 API 额度。

## 部署

上传 GitHub 用于代码版本管理，不会自动上线网页。实际密钥需在部署环境单独配置。公网访问、HTTPS 和使用额度限制在部署环境另行处理。

## 上游来源

`meihua_yi/engine.py` 基于 [handsomejustin/meihua-yi](https://github.com/handsomejustin/meihua-yi)。本项目修正了十二项卦名，并增加本卦与变卦的体用关系数据，时间起卦与六爻算法保持原有规则。上游 MIT 许可证保留在 `meihua_yi/UPSTREAM_LICENSE`。

参考：[Streamlit 文档](https://docs.streamlit.io/)、[DeepSeek API 文档](https://api-docs.deepseek.com/)。
