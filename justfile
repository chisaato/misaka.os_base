# Justfile for misaka Ansible Collection Monorepo

set shell := ["bash", "-uc"]

# 默认执行全部集合的构建与安装
default: all

# 构建并安装全部 Collection
all: build install

# 构建指定的 Collection 或全部 Collection（如：just build uv 或 just build）
build collection="":
    #!/usr/bin/env bash
    set -euo pipefail
    build_one() {
        local coll_dir="$1"
        if [ ! -f "${coll_dir}/galaxy.yml" ]; then
            return 0
        fi
        local namespace name version filename
        namespace=$(uv run yq -r '.namespace' "${coll_dir}/galaxy.yml")
        name=$(uv run yq -r '.name' "${coll_dir}/galaxy.yml")
        version=$(uv run yq -r '.version' "${coll_dir}/galaxy.yml")
        filename="${namespace}-${name}-${version}.tar.gz"

        echo "==> 正在构建集合 ${namespace}.${name} (版本 ${version})..."
        pushd "${coll_dir}" > /dev/null
        uv run ansible-galaxy collection build -f
        mv "${filename}" ../../ 2>/dev/null || true
        popd > /dev/null
        echo "✔ 构建成功: ${filename}"
    }

    if [ -n "{{collection}}" ]; then
        if [ -d "collections/{{collection}}" ]; then
            build_one "collections/{{collection}}"
        else
            echo "错误: 未找到集合 collections/{{collection}}" >&2
            exit 1
        fi
    else
        for coll in collections/*/; do
            build_one "${coll%/}"
        done
    fi

# 安装指定的 Collection 或根目录下已构建好的所有 Collection 包
install collection="":
    #!/usr/bin/env bash
    set -euo pipefail
    install_one() {
        local coll_dir="$1"
        if [ ! -f "${coll_dir}/galaxy.yml" ]; then
            return 0
        fi
        local namespace name version filename
        namespace=$(uv run yq -r '.namespace' "${coll_dir}/galaxy.yml")
        name=$(uv run yq -r '.name' "${coll_dir}/galaxy.yml")
        version=$(uv run yq -r '.version' "${coll_dir}/galaxy.yml")
        filename="${namespace}-${name}-${version}.tar.gz"

        if [ ! -f "${filename}" ]; then
            echo "警告: 未找到安装包 ${filename}，正在尝试自动构建..."
            just build "${name}"
        fi

        echo "==> 正在安装 ${filename}..."
        uv run ansible-galaxy collection install -f "${filename}"
        echo "✔ 成功安装 ${namespace}.${name}:${version}"
    }

    if [ -n "{{collection}}" ]; then
        if [ -d "collections/{{collection}}" ]; then
            install_one "collections/{{collection}}"
        else
            echo "错误: 未找到集合 collections/{{collection}}" >&2
            exit 1
        fi
    else
        for coll in collections/*/; do
            install_one "${coll%/}"
        done
    fi

# 运行 ansible-lint 检查
lint collection="":
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -n "{{collection}}" ]; then
        uv run ansible-lint "collections/{{collection}}/"
    else
        uv run ansible-lint collections/*/
    fi

# 运行单元测试
test-unit:
    uv run pytest collections/os_base/tests/unit/

# 构建/刷新开发用本地 collection symlink 树（.dev/，供 molecule 消费工作区源码）
dev-collections:
    bash shared/scripts/dev-collections.sh

# 运行指定 Molecule 场景测试（例如：just molecule containers docker）
# 自动先刷新 .dev symlink 树，并通过 ANSIBLE_COLLECTIONS_PATH 让姊妹 collection 可解析
molecule collection scenario: dev-collections
    #!/usr/bin/env bash
    set -euo pipefail
    export ANSIBLE_COLLECTIONS_PATH="{{justfile_directory()}}/.dev${ANSIBLE_COLLECTIONS_PATH:+:${ANSIBLE_COLLECTIONS_PATH}}"
    cd "collections/{{collection}}"
    uv run molecule test -s "{{scenario}}"

# 清理根目录下的构建产物
clean:
    rm -f *.tar.gz
