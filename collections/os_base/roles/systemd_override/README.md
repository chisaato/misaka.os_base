# systemd_override

已弃用，推荐调用 `misaka.os_base.logging`。此兼容入口委托 logging 的 `journald` 任务，继续维护原 `/etc/systemd/journald.conf.d/01-persist-storage.conf`，并创建持久 journal 目录；只有配置变化时才通知 journald handler，不执行 daemon-reexec。

仅管理 journald，不安装软件包、不启用 logrotate.timer、不创建轮转规则、不接管 audit。旧变量 `systemd_override_journald_max_usage` 保留，作为 `logging_journald_system_max_use` 的默认来源。
