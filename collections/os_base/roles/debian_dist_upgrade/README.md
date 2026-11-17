# Debian 12→13 在线分阶段升级

默认 `advance` 只准备、切 trixie 源、严格 update、预下载，然后在**安装前暂停**。
这是在线升级，不是 Fedora 的离线事务。仅覆盖空载 Debian 12→13，不是生产安全承诺，也不能用于 PVE。

```yaml
debian_dist_upgrade_action: advance
debian_dist_upgrade_until: downloaded  # 不设置 until 也是此默认；安装前暂停
```

`action: status` 为只读，不创建 marker/执行器或更新索引。推进时 `until` 一次只选择一个：

| until | 显式许可边界 |
|---|---|
| `minimal_upgraded` | 最小安装，无新增/移除 |
| `full_upgraded` | 完整安装，等待重启 |
| `reboot_requested` | 独立许可重启 |
| `completed` | 安装、重启及联合验证 |

`until` 显式值优先于兼容变量 `debian_dist_upgrade_skip_reboot`（保留字面默认 true）。
只把 skip_reboot 改为 false **不会**越过默认安装闸门。重复执行不会倒退或撤销已经发生的安装。
`preflight`/`prepared` 可作为更早暂停点；`verified` 表示允许到联合验证事实边界。

## 命令与配置策略

- [Debian 13 官方 release notes](https://www.debian.org/releases/trixie/release-notes/upgrading.en.html) §4.4.5/4.4.6：先最小再完整升级。
- 官方示例 `apt upgrade --without-new-pkgs` 对应脚本的 `apt-get upgrade`（apt-get 默认不新增、不删除）；额外 `--no-remove`，预先核对模拟计划。不是 `apt-get upgrade --without-new-pkgs`。
- 下载：`apt-get -y --download-only dist-upgrade`；下载前后 dpkg status、info、updates 和日志指纹必须相同。最小升级后 full 计划重新计算，后续仍可能下载，不保证一次预下载绝对完备。
- 完整安装：`apt-get -y dist-upgrade`。最小/完整安装失败不重试；只有 update/下载抗网络抖动重试。
- update 使用 `APT::Update::Error-Mode=any`，任何源失败都阻断（比容忍第三方源更保守），不按固定域名识别主源。
- 非交互：`DEBIAN_FRONTEND=noninteractive`、`--force-confdef` + `--force-confold`（优先默认行为，否则保留旧配置）；`UCF_FORCE_CONFFOLD=1`、`NEEDRESTART_MODE=l`、禁用 apt-listchanges 提问。管理员须之后审阅 `.dpkg-dist`/`.ucf-dist`；不是无损配置合并承诺。
- 不自动 autoremove，不自动 `dpkg --configure -a`/`apt -f install`。

## 事实、人工介入与中断

marker：`/var/lib/misaka/dist-upgrade/debian.json`；0700/0600，共享原子 seq 校验。
systemd oneshot 单元与 `/var/lib/misaka/dist-upgrade/debian-jobs/` 的 active/result/log 脱离 SSH；
Ansible 用 raw + retries/until 观察同一单元，不用 async/poll，也不在 Python 替换窗口加载 Python 模块。
调用 play 必须 `gather_facts: false`（两个随附入口已设置）；角色先 raw 等待已有 worker，再刷新 facts。
否则调用方在角色执行前自行 Gather Facts 仍可能撞上 Python 替换窗口。worker 在安装前预加载 marker 依赖。
控制端中断后重跑会观察现有 worker，而不是重复安装。
也可查询 `systemctl status misaka-debian-*`/`journalctl -u <unit>` 和 job 日志。无结果但单元已停止、非零结果或 dpkg 异常都明确报错。
已有 APT 锁是忙，不称数据库损坏；忙时不执行新的 APT。

人工 `apt-get upgrade`/`apt-get dist-upgrade`/重启后，角色从当前事实收养，不要求旧控制工作目录。
marker 只能提供历史/意图，不抬高实时阶段；下载回执还校验实际 deb 缓存指纹，人工清缓存后须重新下载。
dpkg audit 与状态、APT 待处理计划、源 suites、
实际 `linux-image-amd64` candidate/依赖、已安装内核及运行内核、boot_id 联合验证。
`os-release=13`、`reboot-required` 存在/缺失、某个固定内核版本都不是充分证据。
目标无 marker 时不声称曾重启：建立当前 boot_id 基线后，需显式重启边界才能证明完成。
验证要求标准 amd64 Debian 内核 metapackage，candidate 必须来自目标 suite，不自动接管自定义内核/hold/pinning/第三方 suites。
源系统允许 Packer 基线的 bookworm-backports 源；管理的主源文件切换后不迁移到 trixie-backports，亦不承诺接管已安装的 backports 包。
独立的 backports/第三方源文件不自动删除；若留下混合 suites，则拒绝推进，需管理员审阅。

失败事务需管理员查日志并手工修复；确认系统健康后，保存失败 job 证据，再人工移走
`debian-jobs/active.json` 才能重新评估，不自动忽略失败结果。不要删除正在执行的 active/job。
不接管升级中断电，不保证两个 Play 并发或人与 apt 同时操作的事务安全。
