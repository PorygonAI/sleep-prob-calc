# 宝蓝湖畔概率曲线

输入卡比兽能量和睡眠分数范围（默认 1～100），点击「拉鲁拉丝」「奇鲁莉安」或「沙奈朵」生成至少出现一次该宝可梦的概率曲线。「计算并绘图」使用当前选中的宝可梦。

页面从同目录的 `lapis_lakeside_sleep_styles.csv` 读取睡姿，在 Web Worker 中运行非递归动态规划。无需预先生成、上传或下载概率 bin 文件，现有 bin 仅保留为历史数据。

## 更新数据

需要 Python 3.10+、Git，以及当前电脑对仓库的推送权限，无第三方 Python 依赖。在本仓库或原本的脚本目录运行：

```sh
python run_pipeline.py
```

流程会抓取 RaenonX [宝蓝湖畔地图](https://pks.raenonx.cc/zh/map/5) 和 [Sleepdex](https://pks.raenonx.cc/en/sleepdex/lookup)，校验并更新 CSV，只提交该 CSV，再推送 `origin/main`。GitHub Pages 部署完成后刷新网页即可使用新数据。网页不设数据更新按钮。

```sh
# 只抓取、复制，不提交或推送
python run_pipeline.py --copy-only
# 可显式指定发布仓库和提交信息
python run_pipeline.py --repo-dir PATH --message "Update sleep styles"
```

推送失败时脚本返回非零退出码。重新运行会重试推送，即使 CSV 未发生变化。暂存区已有其他改动或当前分支不是 main 时，流程会停止，避免混入其他提交内容。

## 概率模型

- 保留原有卡比兽等级和睡姿数量阈值，`SPO = floor(能量 × 分数 / 38000)`。
- 只使用已解锁睡姿；普通抽取等概率、有放回，每次睡眠最多一次大肚上睡。
- 末抽排除 `is_leader_exclusion`，优先最大 SPO，同 SPO 取最低等级，再取最小 internalId。
- 沿用原来的固定 10 睡姿无能量池假设：其中一个为拉鲁拉丝，不包含奇鲁莉安、沙奈朵。因此剩余 n 抽的无能量概率分别为 `1 - 0.9^n`、`0`、`0`。
- 高能量下超过「最大睡姿 SPO × 槽位数」后概率不再变化，采用等价上限减少计算量。

## 本地运行与验证

```sh
python -m http.server 8765
# 浏览器打开 http://localhost:8765，避免 file:// 对 Worker/fetch 的限制。
node --test tests/probability.test.js
python -m unittest discover -s tests -p "test_*.py"
```
