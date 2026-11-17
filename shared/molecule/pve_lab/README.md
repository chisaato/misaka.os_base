# PVE 空载实验资产

不是生产升级角色。仅覆盖单节点、无内层 VM/CT、无集群/Ceph/共享存储的 UEFI 实验。

## PVE 8 基线

```sh
python3 shared/scripts/validate_pve_lab.py baseline
```

消费既有 Debian 12.15 local-manifest 成品，不改 Packer。按官方 Debian 12 安装指南先安装并重启到
Proxmox 内核，再执行 `pve_on_debian`/`pve_init`，移除 Debian 内核、重启、独立读事实与角色幂等验证。
每次启动以固定 MAC 的实际 DHCP 租约为准，guest 专用 service 在 pmxcfs 前更新 `/etc/hosts`，不改宿主网络。
初次重启会由 PVE 自身恢复 root authorized_keys 链接，因此重启后先正常 converge，再测第二次 changed=0。

所有证据默认写 `${XDG_STATE_HOME:-$HOME/.local/state}/misaka-os-base/validation/`，目录 0700、日志/清单 0600。
只读基线在 `artifacts/pve8.4-uefi.qcow2`（0400）及同名 `.manifest.yml`；不是日志归档磁盘。
成品保留 PVE 系统自身的 PKI/节点身份，只适用于本地私有、顺序空载实验，不是可公开分发的通用模板。
不单独导出任何私钥或运行 seed；导出前清理 cloud-init 缓存及测试用户的注入公钥。临时磁盘 staging
也使用私有目录及 qemu DAC UID 的具名 ACL，清理只针对本轮所有权清单和专属缓存。

`export-baseline --root <证据目录>` 只续接已安装完成的同一 VM 做核验/导出，不是 APT 半事务恢复。
导出后用新 overlay、seed 和 NVRAM 实际重用一次，要求 machine-id/包状态保持相同、boot_id 改变、服务与 EFI 正常。

## 事实与边界

## PVE 8→9 空载实验

```sh
python3 shared/scripts/validate_pve_lab.py upgrade --root <持久证据目录> --image <只读PVE8基线>
```

`--until preflight|sources|downloaded|installed|completed` 提供显式停顿点。使用同一 `--root` 续接
原 VM，不能另开一台。真实 checker 原始输出逐次保留，FAIL 必须阻断；安装后即使控制端退出，
续跑仍须重新执行重启前 checker。APT 安装阶段不自动重试、不终止事务；失败 worker 保守拒绝重复启动，
须先核对真实进程、锁、日志和数据库。
控制端 SSH 在更新期间重置时，续跑通过持久 `upgrade9-job.json` 核对 guest 活跃 job id，
仅观察原 worker，不重新执行 start；观察时的 255 传输错误与 75 busy 一样等待，不当成 APT 结果。

`upgrade-prerequisites --root <持久证据目录>` 仅响应本实验实际出现的两项 WARN：将空的旧 udev
规则替换为保持 eth0 的 VirtIO `.link`，设置 GRUB removable 路径维护并重装 GRUB，再更新 PVE 缓存和复检。
不删除有内容的 NIC 规则，不通过修改服务或 `/etc/pve` 欺骗 checker。

检查点由干净关机磁盘转换为独立只读 qcow2；导出后的只读核验若中断，续跑先核对 manifest 摘要及
真实 guest 包状态/身份/新 boot_id，并重新执行 checker，不覆盖成品。重启就绪要求四个服务**全部** active。

### 独立事实

`probe.py` 只读 `pveversion`、dpkg audit、APT 待处理计划、服务、pmxcfs FUSE 挂载、EFI 和 hostname。
内核根据 `proxmox-default-kernel` 的实际安装依赖闭包及 `/boot/vmlinuz-$(uname -r)` 所属包验证，
不借用纯 Debian 的 linux-image 判断，也不硬编码 6.8/6.14 等运行版本。
空载安装可能没有 storage.cfg；只读验证目录/FUSE/API，不为验收创建 `/etc/pve` 文件。

`apt_worker.py` 是实验专用的 systemd oneshot 执行器，结果先持久化，观察器沿用纯 shell/retries 模式。
已有 APT/dpkg 忙或 audit 异常会停，不自动修复、不自动重试安装、不自动 autoremove。
不做升级中断电或双 Play 并发验收；检查点只在干净关机后生成。

官方来源：
- https://pve.proxmox.com/wiki/Install_Proxmox_VE_on_Debian_12_Bookworm
- https://pve.proxmox.com/wiki/Upgrade_from_8_to_9

PVE no-subscription 官方索引使用文档列出的 HTTP 入口时，额外以官方公开签名密钥、InRelease 签名与
Packages SHA256 核对版本；不通过忽略 TLS 验证错误解决官方 download 域名的证书不匹配。
