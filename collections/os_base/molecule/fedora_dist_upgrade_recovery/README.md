# Fedora 43→44 无负载 UEFI 恢复测试

运行 `just molecule os_base fedora_dist_upgrade_recovery`。只使用场景自己的 VM，不修改宿主网络。

`prepare_upgrade.yml` 建立真实 Fedora 43 prepared 状态；`staged.py` 使用原角色和独立控制机进程做：

- R1 的限定注入：download intent 已写、dnf 尚未启动时 SIGKILL。**不等同于下载进行中断线**。
- R4：普通重启，OS 仍为 43，待办事务仍为 44，再跑 downloaded 不改 marker。
- R7：真实执行 `dnf5 offline clean`，角色降级并重新下载。
- R2：重启 intent 已落盘、offline reboot 尚未调用时 SIGKILL。
- R3：offline reboot 完成、客户机为 44、verify 尚未执行时 SIGKILL；新控制机继续，不再重启。

之后 `run.py` 使用升级完成的系统做 R9/R10 的拒绝且无副作用断言、完整 advance 入口的 R12/R13 并发与租约接管、R6 收尾前中断、R8 的落后 marker 收养、R11 的真实 jsonfile 旧缓存。

测试 callback 仅由测试进程的环境变量启用。没有给生产角色增加故障注入变量。每次日志目录独立，结果写入 `staged-results.json` 和 `results.json`。

覆盖边界：R6 在第一个清理任务前杀控制机，不是制造 rpm 清理命令内部失败；R8 是真实已升级系统上注入落后 marker，不代表另做了一次全人工升级。R12/R13 的完整角色并发在 completed 事实下执行，不能外推到下载/重启窗口或人手动 dnf 并发。R5、R14 的断电/半事务注入尚未覆盖。目录锁探针不是这些事务用例的替代品。
