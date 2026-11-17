# logging

管理 journald，以及 Fedora 43/44、Debian 12/13 的 logrotate 包、timer 和自定义规则。其他发行版仅管理 journald。由 `common_init` 调用，也可独立使用。

## 文件所有权

- journald 的唯一配置所有者：沿用 `/etc/systemd/journald.conf.d/01-persist-storage.conf`，创建 `/var/log/journal`（root:systemd-journal，2755）。
- **不覆盖 `/etc/logrotate.conf`**：沿用发行版主文件中的 `include /etc/logrotate.d`。
- 自定义轮转规则只写 `/etc/logrotate.d/misaka-logging-<name>`；此命名空间由本角色保留，不覆盖发行版或其他包的规则。
- 不安装 rsyslog；**不安装、配置或操作 audit/auditd**，系统原有审计配置及服务保持原样。
- 不尝试恢复历史版本已覆盖的真实机器文件；本次变更仅停止接管。

## journald 变量

| 变量 | 默认值 |
| --- | --- |
| `logging_journald_storage` | `persistent` |
| `logging_journald_compress` | `true` |
| `logging_journald_system_max_use` | 旧变量 `systemd_override_journald_max_usage`，未设置时 `4G` |
| `logging_journald_system_keep_free` | `1G` |
| `logging_journald_runtime_max_use` | `50M` |
| `logging_journald_max_retention_sec` | `1month` |
| `logging_journald_max_file_sec` | `1month` |
| `logging_journald_sync_interval_sec` | `5m` |
| `logging_journald_forward_to_syslog` | `false` |

## 自定义轮转规则

`logging_logrotate_rules` 默认 `[]`（不为未知应用日志创建规则）。每项包含 `name`、`paths`，可选 `options`。名称仅允许字母、数字、下划线、连字符。

省略 `options` 时每条规则使用 `weekly`、`rotate 4`、`compress`、`dateext`、`missingok`、`notifempty`。显式提供 `options` 会替换该条规则的全部默认选项，调用方应提供完整合理的策略。列表移除项不会自动删除旧文件，避免误删数据；需要显式清理本角色命名空间中不再需要的规则。

```yaml
- hosts: all
  roles:
    - role: misaka.os_base.logging
      logging_logrotate_rules:
        - name: myapp
          paths:
            - /var/log/myapp/*.log
```

该示例写入 `/etc/logrotate.d/misaka-logging-myapp`。请不要将系统已经轮转的日志再纳入自定义规则，避免重复匹配。

## 兼容入口与测试

`misaka.os_base.systemd_override` 已弃用，但通过 `include_role: logging` 的 `tasks_from: journald` 继续管理 journald；不会经旧入口安装包、修改 timer 或创建轮转规则。旧容量变量继续有效。

`logging_fedora`（43/44）和 `logging_debian`（12/13）共享 prepare/converge/verify：先验证兼容入口，再安装测试夹具并记录发行版主配置、auditd 配置和原有轮转规则 SHA-256；验证角色没有修改它们、没有引入额外软件包，仅新增两份命名空间规则，并检查 journal、timer、`logrotate -d` 和幂等性。audit 包仅由测试 prepare 安装作为防误改夹具，不属于角色职责。
