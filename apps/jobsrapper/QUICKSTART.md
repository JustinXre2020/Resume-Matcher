# Job Hunter Sentinel - 快速参考

## 📂 项目文件

```
jobsrapper/
├── 📝 核心脚本
│   ├── main.py              # 主程序入口
│   ├── scraper.py           # 职位抓取引擎
│   ├── ai_analyzer.py       # Gemini AI 分析器
│   ├── database.py          # 去重与持久化
│   └── email_sender.py      # 邮件发送模块
│
├── ⚙️ 配置文件
│   ├── pyproject.toml       # 项目配置 (uv)
│   ├── requirements.txt     # 依赖列表
│   ├── requirements.lock    # 锁定版本
│   ├── .env.example         # 环境变量模板
│   ├── .python-version      # Python 版本
│   └── .gitignore          # Git 忽略规则
│
├── 🛠️ 工具脚本
│   ├── setup.sh            # 一键安装脚本
│   └── test_deps.py        # 依赖测试脚本
│
├── 📚 文档
│   ├── README.md           # 完整文档
│   └── MIGRATION.md        # uv 迁移说明
│
└── 🔒 虚拟环境
    └── .venv/              # Python 虚拟环境 (git 忽略)
```

## 🚀 常用命令

### 初始设置
```bash
# 一键安装
./setup.sh

# 或手动安装
uv venv .venv
uv pip install -e .
source .venv/bin/activate
```

### 日常使用
```bash
# 激活虚拟环境
source .venv/bin/activate

# 运行主程序
python main.py

# 测试各模块
python scraper.py
python ai_analyzer.py
python database.py
python email_sender.py

# 测试依赖
python test_deps.py
```

### 依赖管理
```bash
# 添加新依赖
uv pip install package-name

# 更新依赖
uv pip install -e . --upgrade

# 查看已安装
uv pip list

# 锁定版本
uv pip freeze > requirements.lock
```

### 退出虚拟环境
```bash
deactivate
```

## 🔑 环境变量配置

编辑 `.env` 文件：

```env
# 必填
GEMINI_API_KEY=your_key_here
RESEND_API_KEY=your_key_here
RECIPIENT_EMAIL=your@email.com

# 可选
DATABASE_URL=sqlite:///./jobs.db
SEARCH_TERMS=software engineer,ml engineer
LOCATIONS=San Francisco CA,New York NY
RESULTS_WANTED=20
HOURS_OLD=24
MIN_SCORE=6
```

## 🤖 GitHub Actions 配置

需要在 GitHub 仓库中配置：

### Secrets (必填)
- `GEMINI_API_KEY`
- `RESEND_API_KEY`
- `RECIPIENT_EMAIL`

### Variables (可选)
- `SEARCH_TERMS`
- `LOCATIONS`
- `RESULTS_WANTED`
- `HOURS_OLD`
- `MIN_SCORE`

## 📊 程序运行流程

```
1. 抓取职位 (scraper.py)
   ↓
2. AI 分析评分 (ai_analyzer.py)
   ↓
3. 分数过滤 (>= MIN_SCORE)
   ↓
4. 去重检查 (database.py)
   ↓
5. 邮件推送 (email_sender.py)
   ↓
6. 标记已发送 (database.py)
```

## 🐛 故障排除

### 依赖导入失败
```bash
# 重新安装依赖
uv pip install -e . --force-reinstall
```

### 虚拟环境问题
```bash
# 删除并重建
rm -rf .venv
uv venv .venv
uv pip install -e .
```

### API 错误
- 检查 `.env` 中的 API keys 是否正确
- 确认 API 配额是否充足
- 查看 Gemini/Resend 控制台日志

### 429 速率限制
- 程序会自动重试 (最多 3 次)
- 检查 `scraper.py` 中的延迟设置
- 考虑减少 `RESULTS_WANTED`

## 📞 获取帮助

- 查看完整文档: `README.md`
- 查看迁移说明: `MIGRATION.md`
- 提交 Issue: GitHub Issues
- 查看日志: 程序输出详细日志

## ✨ 快速测试

```bash
# 完整测试流程
cd apps/jobsrapper
./setup.sh
source .venv/bin/activate
python test_deps.py  # 验证依赖
# 配置 .env 文件
python main.py      # 运行主程序
```

祝您职位搜索顺利！🎯
