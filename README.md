# misaka Ansible Collections

一个围绕 Linux 服务器基础初始化、容器运行时配置与 Python CLI 工具链声明式管理的 Ansible Collection Monorepo。

## 包含的 Collection

| Collection | 路径 | 当前版本 | 说明 |
| --- | --- | --- | --- |
| `misaka.os_base` | [`collections/os_base/`](collections/os_base/) | `1.13.0` | 操作系统基础初始化（软件源、基础配置、zsh、日志、Btrfs、PVE、跨大版本在线升级等） |
| `misaka.containers` | [`collections/containers/`](collections/containers/) | `1.3.0` | 容器环境安装与配置（Docker CE、Podman 及镜像加速） |
| `misaka.uv` | [`collections/uv/`](collections/uv/) | `0.1.0` | 基于 `uv tool` 的用户级 Python CLI 声明式管理 |

## 支持环境

- **最低 Ansible 版本**：`>= 2.15.0`
- **支持发行版**：Debian 最新 2 个版本、Fedora 最新 2 个版本、AlmaLinux 9（部分角色开发中）、Proxmox VE（基于 Debian）

## 设计特点

- **China-First 与网络自适应**：通过 `host_geo.country`（默认 `'cn'`）决定使用国内镜像站还是官方上游源；国内镜像站均采用可覆盖列表设计。
- **空安全与直连回退**：未配置第三方镜像加速时，模板会自动生成合法空配置或回退官方直连域名，不会因变量为空而报错。
- **幂等与诚实变更**：写操作先探测后执行，拒绝使用 `changed_when: false` 掩盖真实变更。
- **在线跨版本升级**：内置 `debian_dist_upgrade` 与 `fedora_dist_upgrade`，基于状态机与锁机制支持分阶段升级与故障恢复。

## 快速开始

### 1. 本地构建与安装

仓库使用 [`just`](https://github.com/casey/just) 与 [`uv`](https://github.com/astral-sh/uv) 管理依赖与构建（构建产物为根目录下的 `*.tar.gz`）：

```bash
# 同步 Python / Ansible 工具链
uv sync

# 一键构建并安装全部 Collection 到本地
just all

# 或按单个 Collection 构建与安装
just build os_base
just install os_base
```

如果不使用 `just`，也可直接使用 `ansible-galaxy`：

```bash
ansible-galaxy collection build collections/os_base/ -f
ansible-galaxy collection install misaka-os_base-*.tar.gz -f
```

### 2. 在 Playbook 中使用

```yaml
- name: 初始化系统与容器环境
  hosts: all
  vars:
    host_geo:
      country: cn
  roles:
    - misaka.os_base.auto_init
    - misaka.containers.docker
```

更多入口 Playbook 与变量说明请参考各 Collection 及 Role 目录下的 `README.md`。

---

## 镜像与反代配置说明

* `misaka.containers.docker` 的第三方 Registry 加速（`docker_podman_registry_mirror`）默认留空 `{}`，`misaka.os_base.zsh` 的 GitHub/GitLab 代理变量（`zsh_github_repo_mirror_cn`、`zsh_gitlab_repo_mirror_cn`）默认置空 `""`。
* 未配置时自动回退为官方直连；如需使用自建反代，请在调用方的 `group_vars` 或 `host_vars` 中自行填充覆盖，配置范例见 [`collections/containers/roles/docker/README.md`](collections/containers/roles/docker/README.md) 与 [`collections/os_base/roles/zsh/README.md`](collections/os_base/roles/zsh/README.md)。

---

## 开发、测试与发布

项目的仓库规范、Lint 检查、单元测试、Molecule 虚拟机测试以及发布流程全部记录在 [`AGENTS.md`](AGENTS.md) 中。
