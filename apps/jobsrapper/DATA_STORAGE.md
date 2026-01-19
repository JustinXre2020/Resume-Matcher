# Job Hunter Sentinel - 数据存储与定时任务配置

## 🎯 新增功能

### 1. 本地数据存储

所有抓取的岗位数据将自动保存到 `data/` 文件夹：

```
data/
├── jobs_2026-01-18_08-00.json  # JSON 格式（包含完整元数据）
├── jobs_2026-01-18_08-00.csv   # CSV 格式（便于分析）
├── jobs_2026-01-18_12-00.json
├── jobs_2026-01-18_12-00.csv
└── ...
```

**文件命名规则**: `jobs_YYYY-MM-DD_HH-MM.json/csv`

### 2. 自动数据清理

- ✅ 每次运行时自动清理 **7天前** 的旧数据
- 📊 保持数据文件夹大小可控
- 🔄 在 `main.py` 中自动执行

### 3. 定时任务调度

#### 方式一：本地 Cron（推荐用于服务器）

**安装定时任务**：
```bash
cd apps/jobsrapper
./install_cron.sh
```

这将设置每天 3 次自动抓取：
- 🌅 **8:00 AM** - 早间抓取
- 🏙️ **12:00 PM** - 午间抓取
- 🌆 **6:00 PM** - 晚间抓取

**卸载定时任务**：
```bash
./uninstall_cron.sh
```

**查看当前任务**：
```bash
crontab -l
```

**查看日志**：
```bash
tail -f logs/cron_08.log   # 查看 8点的运行日志
tail -f logs/cron_12.log   # 查看 12点的运行日志
tail -f logs/cron_18.log   # 查看 18点的运行日志
```

#### 方式二：GitHub Actions（云端自动化）

已更新 `.github/workflows/job_hunter.yml`，支持每天 3 次运行：
- 🌅 **8:00 AM** Eastern Time (UTC 13:00)
- 🏙️ **12:00 PM** Eastern Time (UTC 17:00)
- 🌆 **6:00 PM** Eastern Time (UTC 23:00)

数据将自动：
- 📤 上传为 GitHub Artifacts（保留 14 天）
- 💾 提交到 Git 仓库（可选）

## 📊 数据管理功能

### 查看数据统计

```python
from data_manager import DataManager

manager = DataManager()
stats = manager.get_statistics()

print(f"Total files: {stats['total_files']}")
print(f"Total jobs: {stats['total_jobs']}")
print(f"Storage size: {stats['total_size_mb']:.2f} MB")
```

### 列出所有数据文件

```python
files = manager.list_data_files('json')  # 或 'csv'
for f in files:
    print(f.name)
```

### 手动清理旧数据

```python
# 清理 7 天前的数据
deleted = manager.cleanup_old_files(days=7)

# 清理 30 天前的数据
deleted = manager.cleanup_old_files(days=30)
```

### 合并所有数据

```python
# 将所有 JSON 文件合并为一个 CSV
manager.merge_all_jobs(output_file="all_jobs_combined.csv")
```

## 🗂️ 数据文件格式

### JSON 格式
```json
{
  "timestamp": "2026-01-18T08:00:00",
  "count": 20,
  "jobs": [
    {
      "title": "Senior Software Engineer",
      "company": "Google",
      "location": "San Francisco, CA",
      "job_url": "https://...",
      "description": "...",
      "site": "linkedin",
      "date_posted": "2026-01-18",
      ...
    }
  ]
}
```

### CSV 格式
标准 CSV 文件，包含所有职位字段，可用 Excel、Pandas 等工具分析。

## 🔧 配置选项

### 修改清理周期

编辑 `main.py` 中的清理天数：
```python
# 从 7 天改为 14 天
self.data_manager.cleanup_old_files(days=14)
```

### 修改定时任务时间

编辑 `install_cron.sh` 中的 cron 表达式：
```bash
# 格式: 分 时 日 月 星期
CRON_JOB_08="0 8 * * * ..."   # 每天 8:00
CRON_JOB_12="0 12 * * * ..."  # 每天 12:00
CRON_JOB_18="0 18 * * * ..."  # 每天 18:00
```

### 修改 GitHub Actions 时间

编辑 `.github/workflows/job_hunter.yml`：
```yaml
schedule:
  - cron: '0 13 * * *'  # UTC 13:00 = ET 8:00 AM
  - cron: '0 17 * * *'  # UTC 17:00 = ET 12:00 PM
  - cron: '0 23 * * *'  # UTC 23:00 = ET 6:00 PM
```

## 📝 使用示例

### 完整运行流程

```bash
# 1. 确保虚拟环境已激活
source .venv/bin/activate

# 2. 运行程序（会自动保存数据）
python main.py

# 3. 查看保存的数据
ls -lh data/

# 4. 安装定时任务（可选）
./install_cron.sh
```

### 测试数据管理模块

```bash
# 测试数据保存和统计
python data_manager.py
```

## 🎯 数据保留策略

- ✅ **实时数据**: 最近 7 天的数据保留在本地
- 📤 **GitHub Artifacts**: 14 天保留期
- 💾 **Git 仓库**: 永久保留（可选，需配置）
- 🗑️ **自动清理**: 每次运行时清理 7 天前的数据

## 🔒 数据安全

- 📁 `data/` 文件夹已添加到 `.gitignore`
- 🔐 本地数据不会意外提交到公共仓库
- 🎯 GitHub Actions 中可选择是否提交数据

## 📊 数据分析建议

可以使用以下工具分析保存的数据：

1. **Python Pandas**
   ```python
   import pandas as pd
   df = pd.read_csv('data/jobs_2026-01-18_08-00.csv')
   print(df.describe())
   ```

2. **Excel/Google Sheets**
   - 直接打开 CSV 文件
   - 进行筛选、排序、图表分析

3. **数据库导入**
   - 可将 CSV 导入 MySQL、PostgreSQL 等
   - 进行更复杂的查询和分析

## ✅ 验收清单

- [x] 数据自动保存到 `data/` 文件夹
- [x] 同时生成 JSON 和 CSV 格式
- [x] 文件名包含时间戳
- [x] 7 天自动清理功能
- [x] 本地 cron 定时任务脚本
- [x] GitHub Actions 支持 3 次/天
- [x] 数据统计和管理功能
- [x] 完整的安装/卸载脚本

---

**快速开始**: 运行 `./install_cron.sh` 设置定时任务，数据将自动保存到 `data/` 文件夹！
