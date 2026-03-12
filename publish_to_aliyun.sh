#!/bin/bash
set -e

# 确保脚本始终在包含 Dockerfile 的同级目录下运行
cd "$(dirname "$0")"

# 默认地域为杭州，如果是其他地域（如北京、上海等），请修改此处（例如：cn-beijing）
# 使用用户指定的阿里云 ACR 个人版地址
REGISTRY="crpi-71isp0aellmb4yns.cn-hangzhou.personal.cr.aliyuncs.com"
NAMESPACE="oneclaw0312"
IMAGE_NAME="oneclaw-web"
VERSION="v1"
FULL_IMAGE_NAME="${REGISTRY}/${NAMESPACE}/${IMAGE_NAME}:${VERSION}"

echo "================================================="
echo "准备推送镜像到阿里云 ACR"
echo "账号: xiaolanxiaolanxiao"
echo "命名空间: ${NAMESPACE}"
echo "目标镜像: ${FULL_IMAGE_NAME}"
echo "================================================="

# 检查 docker 命令是否存在
if ! command -v docker &> /dev/null; then
    echo "❌ 错误: 当前电脑没有安装 Docker。"
    echo "请先在 Mac 上安装 Docker Desktop 或 OrbStack，然后再次运行此脚本。"
    exit 1
fi

echo "1. 正在登录阿里云容器镜像服务..."
echo "请输入你的阿里云 ACR 密码（固定密码或临时密码）："
sudo docker login --username=xiaolanxiaolanxiao ${REGISTRY}

echo ""
echo "2. 正在构建 Docker 镜像，这可能需要几分钟的时间..."
sudo docker build -t ${FULL_IMAGE_NAME} .

echo ""
echo "3. 正在推送镜像到阿里云..."
sudo docker push ${FULL_IMAGE_NAME}

echo ""
echo "✅ 成功！镜像已推送到: ${FULL_IMAGE_NAME}"
echo "你现在可以在阿里云 ECI 控制台中使用该镜像创建容器组了。"
