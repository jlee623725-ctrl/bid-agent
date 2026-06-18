# CLAUDE.md

## 语言与工具链
- Python 3.11+
- 包管理：pip + requirements.txt

## 代码风格
- 所有函数/方法必须添加 type hints
- 公共函数/类使用 docstring 描述用途、参数和返回值
- 单文件不超过 300 行，超出需拆分模块

## 数据库
- 使用 SQLite
- 通过 csv → SQLite 脚本初始化数据库和表结构

## Agent 框架
- 纯 Python 实现
- 使用 OpenAI SDK function calling 模式
- 兼容 DeepSeek API

## 模型
- 默认模型：deepseek-chat

## 配置
- 使用 .env 文件管理环境变量
- 必须包含：DEEPSEEK_API_KEY、DEEPSEEK_BASE_URL

## UI
- 使用 Streamlit 构建前端界面

## 日志
- 使用 logging 模块
- 关键步骤必须记录日志

## 测试
- 使用 pytest
- 核心逻辑必须有对应测试覆盖
