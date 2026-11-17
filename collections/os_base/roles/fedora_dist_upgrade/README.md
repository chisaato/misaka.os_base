# fedora_dist_upgrade

把 Fedora 升到下一个稳定大版本。进度写在目标机的 `/var/lib/misaka/dist-upgrade/fedora.json`。每次运行先读 `os-release`、`boot_id` 和 `dnf5 offline status`，marker 不能声称事实里还没有的阶段。

## 变量

| 变量 | 默认 | 含义 |
|---|---|---|
| `fedora_dist_upgrade_action` | `advance` | `status` 只读；`advance` 向前；`abandon` 归档活动 marker |
| `fedora_dist_upgrade_until` | 不设 | `preflight`、`prepared`、`downloaded`、`reboot_requested`、`verified`、`completed` |
| `fedora_dist_upgrade_target_release` | `44` | 未批准前不改。活动 marker 的目标优先，显式冲突则拒绝 |
| `fedora_dist_upgrade_skip_reboot` | `true` | 弃用别名。没设 `until` 且为 true 时，下载后暂停，**不再跑 post** |
| `fedora_dist_upgrade_abandon_confirm` | 空 | 必须等于当前 `operation_id` |
| `fedora_dist_upgrade_retry_reboot` / `fedora_dist_upgrade_retry_confirm` | false / 空 | 只有 offline 重启失败后，两者同时匹配才允许再重启 |

`status` 不创建 `/var/lib/misaka`。人已经下载了与 marker 目标一致的离线事务时，角色收养，不重新下载。事务被清掉则把 marker 降回 `prepared`。

已在目标版本、且没有 marker 的机器仍执行 post/finalize。这是 D4 的兼容行为，不是新的默认跳过。

## 人工介入

- 想停在下载完成：`-e fedora_dist_upgrade_until=downloaded`
- 想看状态：`-e fedora_dist_upgrade_action=status`
- 目标冲突或 machine-id 不符：用 `abandon`，并带上精确的 `fedora_dist_upgrade_abandon_confirm`
- offline 重启后又回到旧版本且事务还在：角色停止。确认日志后才设置 retry 变量

目录锁从事务探测前持有到暂停或结束，跨 offline reboot 保留 `lock.d`。`flock` 只串行化锁元数据的短窗口，不充当整个 Ansible 事务锁。租约默认覆盖重启超时并留 900 秒余量；控制机被 SIGKILL 后，等待租约过期且无 dnf/rpm 工作进程才接管。正常任务失败由 `always` 释放本次 token 的锁。

已完成系统上曾运行两个真实 `ansible-playbook advance`：持锁控制机暂停后，另一控制机拒绝且 marker、boot_id 不变；杀控制机并等待租约过期后可接管。这个证据不覆盖下载/重启窗口或手动 dnf 并发。详见恢复场景 README 和本地 tracker，不把目录锁探针说成事务验证。

`tested_profile` 在更换控制机时保留；空默认值不会覆盖已有测试描述。离线事务读取 `offline-transaction-state.toml`，不依赖本地化状态文案。`transaction-incomplete` 停止为 `needs_human`，不自动修复。`status` 不调用可能创建 offline 目录的 dnf5 子命令。

## 空载测试

Molecule 场景 `fedora_dist_upgrade` 使用官方 Cloud Base Generic 43，UEFI，无第三方仓库、无负载。结果不能外推到生产机。
