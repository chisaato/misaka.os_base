# misaka.os_base

常见 Linux 发行版的系统基础初始化集合：软件源、系统配置、Proxmox VE 安装等。

## 角色清单

| 角色 | 说明 |
| --- | --- |
| `debian_repo` | Debian apt 源配置（国内镜像/官方，Legacy 与 DEB822 格式），支持跨版本渲染目标版本源 |
| `debian_init` | Debian 系统基础初始化 |
| [`debian_dist_upgrade`](roles/debian_dist_upgrade/README.md) | Debian 12→13 在线分阶段升级；默认下载后、安装前暂停，不用于 PVE |
| `fedora_repo` | Fedora dnf 源与 RPMFusion 配置 |
| `fedora_init` | Fedora 系统基础初始化 |
| `fedora_dist_upgrade` | Fedora 跨大版本升级 |
| `alma_repo` | AlmaLinux 镜像源（开发中） |
| `pve_on_debian` | 在 Debian 上安装 Proxmox VE |
| `pve_init` | PVE 节点初始化（订阅源清理、hosts、IPv4 转发等） |
| `auto_init` | 按发行版自动串接初始化角色 |
| `common_init` | 通用初始化（如 TCP BBR） |
| `btrfs` | btrfsmaintenance 配置 |
| `logging` | journald；Fedora、Debian 的 logrotate 包/timer 与命名空间自定义规则，不接管 audit 或发行版轮转配置 |
| `systemd_override` | 已弃用的 journald 兼容入口，委托 `logging`，不引入包安装或轮转变更 |
| `zsh` | zsh 环境 |

## host_geo 变量

角色通过 `host_geo.country` 判断是否使用国内镜像：

```yaml
host_geo:
  country: cn
```

- 设置为 `cn` 时使用国内镜像站（默认值，未设置时等同于 `cn`）
- 其他值（如 `us`）走官方源

## 支持的发行版

- Debian 最新 2 个版本
- Fedora 最新 2 个版本
- AlmaLinux 9
- Proxmox VE（Debian 底座）

## 最小使用示例

```yaml
- hosts: all
  vars:
    host_geo:
      country: cn
  roles:
    - misaka.os_base.debian_repo
```

更多入口见 `playbooks/`（如 `debian_init.yml`、`fedora_init.yml`、`pve_init.yml`）。
