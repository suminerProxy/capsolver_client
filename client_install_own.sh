#!/bin/bash

echo "=== Client 安装脚本 ==="

# 用户传参
read -p "请输入 Worker Name (默认 test): " worker_name
worker_name=${worker_name:-test}

final_wss_url="wss://capsolver.yxschool.cc:8998/ws/worker/"
# 生成 client/config/config.yaml
mkdir -p client/config
cat > client/config/config.yaml <<EOF
concurrency: null

camoufox:
  api_key: "test"
  solver_type:
    - ImageToTextTask
    - AntiTurnstileTaskProxyLess
  headless: "true"

worker:
  name: "$worker_name"
  wss_url: "$final_wss_url"
EOF

echo "✅ 已生成 client/config/config.yaml"

# 启动 client 容器
echo "🚀 正在启动 client 容器..."
docker compose up -d client
echo "✅ client 容器已启动"