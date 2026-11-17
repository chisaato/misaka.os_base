#!/usr/bin/env bash
# 幂等创建开发用本地 collection symlink 树：
#   <repo_root>/.dev/ansible_collections/misaka/{os_base,containers,uv}
#   -> <repo_root>/collections/<name>
# 供 molecule / ansible-playbook 通过 ANSIBLE_COLLECTIONS_PATH 直接消费工作区源码，
# 无需经 galaxy 拉取（misaka.* 未发布）。
set -euo pipefail

# 仓库根 = 本脚本 shared/scripts/ 的上两级
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
dev_root="${repo_root}/.dev/ansible_collections/misaka"

for name in os_base containers uv; do
    src="${repo_root}/collections/${name}"
    dst="${dev_root}/${name}"

    if [ ! -d "${src}" ]; then
        echo "错误: 源 collection 目录不存在: ${src}" >&2
        exit 1
    fi

    mkdir -p "$(dirname "${dst}")"

    # 幂等：已是正确的 symlink 则跳过，否则重建
    if [ -L "${dst}" ] && [ "$(readlink "${dst}")" = "${src}" ]; then
        continue
    fi
    rm -rf "${dst}"
    ln -s "${src}" "${dst}"
    echo "已创建链接: ${dst} -> ${src}"
done

echo "✔ 开发用 collection symlink 树就绪: ${repo_root}/.dev"
