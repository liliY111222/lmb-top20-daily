# Lithium Metal Battery Papers - Materials Top 20

这是一个可部署到 GitHub Pages 的静态网站，用来追踪图片中材料科学影响因子前 20 个期刊里的锂金属电池论文。

## 关注范围

- 期刊：`data/journals_materials_top20.txt` 中列出的前 20 个材料期刊。
- 主题：lithium metal battery、Li metal anode、anode-free lithium、lithium plating/stripping、lithium dendrite、solid-state lithium metal battery 等。
- 数据源：OpenAlex API，不需要 API key。

## 部署到 GitHub Pages

1. 新建一个 GitHub 仓库，例如 `lmb-top20-daily`。
2. 把本文件夹里的全部内容上传到仓库根目录。
3. 打开仓库 `Settings -> Pages`。
4. 在 `Build and deployment` 里选择 `GitHub Actions`。
5. 进入 `Actions` 页面，手动运行 `Update lithium-metal battery papers`。

成功后，网页地址通常是：

```text
https://你的GitHub用户名.github.io/lmb-top20-daily/
```

## 自动更新

`.github/workflows/update.yml` 已经配置了每天自动更新一次。当前时间是 UTC 22:15，对中国时间大约是每天 06:15。

## 本地更新

```bash
python scripts/lmb_top20_daily.py --days 90 --max-results 120 --output .
```

