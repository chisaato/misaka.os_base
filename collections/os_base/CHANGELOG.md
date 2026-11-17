# Changelog

## Unreleased

- PVE 安装：增加 hostname 非回环前置、bookworm 官方签名密钥摘要校验、下载/包安装重试与 chrony；PVE 初始化统一发行版守卫、China-First 默认及缓存幂等。新增空载 UEFI PVE 8 基线/只读成品重用实验资产与专属私有 staging，不作为生产升级功能
- `debian_dist_upgrade`：从只切源扩展为 Debian 12→13 在线阶段；默认严格 update/下载后在安装前暂停，显式 `until` 才允许最小/完整安装与独立重启。保留 `skip_reboot: true` 默认，`until` 优先，单独 false 不授权安装。guest systemd worker 隔离 SSH 中断；事实收养/联合验证，不自动修复 dpkg 或 autoremove
- `fedora_dist_upgrade`：事实优先的阶段 marker、`action`/`until`，以及目录锁。`skip_reboot: true` 且未设置 `until` 时在下载完成后暂停，不再执行 post（D3 兼容方案，默认字面量仍是 true）。已在目标版本且没有 marker 的机器仍会跑 post（D4，未改默认）。目标版本默认仍是 44
- 新增 `dist_upgrade_state`：发行版中立的 marker 判定和目录锁脚本。锁在票 04 的并发用例通过前只称为设计目标
- libvirt 测试驱动改为显式 UEFI pflash，支持 `debian-html`、`fedora-checksum` 和 `local-manifest`。NVRAM 放在运行目录，不用 `undefine --nvram`
- 新增 `logging`：所有发行版统一 journald 持久化与容量治理；Fedora 43/44、Debian 12/13 管理 logrotate 包、timer 及 `misaka-logging-*` 自定义规则，不覆盖发行版主配置或原有规则
- 不接管 audit：撤去 audit 包安装、配置模板、服务操作及相关变量；系统已有审计组件保持原样，不自动恢复历史配置
- `common_init` 改用 `logging`；`systemd_override` 弃用并委托 logging 的 journald 任务，兼容旧容量变量及 drop-in 路径，不引入包安装或轮转变更
- 新增 Podman systemd 场景 `logging_fedora`（43/44）与 `logging_debian`（12/13），覆盖原有配置校验和不变、命名空间规则、兼容入口及 0 changed 幂等验证

## 1.12.0

- 统一集合元数据：author `chisaato`、license `GPL-2.0-or-later`、最低 Ansible 版本 `>=2.15.0`
- `debian_repo`：新增目标版本渲染契约变量 `debian_repo_target_codename` / `debian_repo_target_major_version`，供 `pve_on_debian`、`debian_dist_upgrade` 等跨版本渲染 apt 源；删除版本检测死代码；增加发行版守卫
- `fedora_repo`：dnf5（Fedora >= 41）系统引导安装 `python3-libdnf5`；删除调试遗留；变量统一 `fedora_repo_` 前缀
- `alma_repo`：清理从 `fedora_repo` 误拷贝的 defaults，元数据对齐标准
- `pve_on_debian`：Debian 系统源渲染改为复用 `debian_repo`；PVE 安装源配置数据驱动化（合并 debian-11/12/13 任务）；新增 `pve_on_debian_manage_resolv_conf`、`pve_on_debian_full_upgrade` 开关
- `pve_init`：`pve_hosts` 更名 `pve_init_hosts`；sysctl 改写 drop-in `/etc/sysctl.d/90-pve_init.conf`
- `btrfs`：元数据与注释修正
