#!/bin/zsh

set -u

PROJECT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$PROJECT_DIR" || {
  print "无法打开英语音频学习助手项目目录。"
  print "按回车键关闭窗口。"
  read -r
  exit 1
}

fail_and_wait() {
  print ""
  print "第一次设置未完成：$1"
  print "请把上面的错误信息告诉 Codex，但不要发送 Notion 访问密钥。"
  print "按回车键关闭窗口。"
  read -r
  exit 1
}

SYSTEM_PYTHON="$(command -v python3 || true)"
if [[ -z "$SYSTEM_PYTHON" ]]; then
  fail_and_wait "未找到 Python 3。请让 Codex 帮助安装 Python 3。"
fi

VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"
if [[ ! -x "$VENV_PYTHON" ]]; then
  print "正在准备本地运行环境..."
  "$SYSTEM_PYTHON" -m venv "$PROJECT_DIR/.venv" ||
    fail_and_wait "无法创建项目内运行环境。"
fi

if ! "$VENV_PYTHON" -c "import notion_client" >/dev/null 2>&1; then
  print "正在安装项目依赖..."
  "$VENV_PYTHON" "$PROJECT_DIR/scripts/bootstrap_environment.py" --skip-tests ||
    fail_and_wait "项目依赖安装失败。请检查网络连接。"
fi

"$VENV_PYTHON" "$PROJECT_DIR/scripts/first_time_setup.py"
SETUP_STATUS=$?

if [[ $SETUP_STATUS -ne 0 ]]; then
  fail_and_wait "请根据上方提示修复后重新双击 start_setup.command。"
fi

print ""
print "设置窗口可以关闭。按回车键结束。"
read -r
exit 0
