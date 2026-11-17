# Molecule 容器测试指南

> 当前状态（2026-10-23）：`misaka.containers` 的 `docker`（Debian 12/13）与 `podman_fedora`（Fedora 42）均已真实全流程通过，幂等均为 **0 changed**。宿主代理问题已修复，Fedora 重跑成功；`just lint containers` 为 **0 failure / 0 warning**。
> 本文档记录如何自行执行、如何判读结果、出问题怎么排查。

## VM 最近上下文与串口证据

libvirt 场景从启动起把串口输出写入运行清单的 `serial_log`，relaunch 以 append 模式继续写，便于关联重启前后上下文。运行时可用 `sudo tail -n 200 -f <清单中的 serial_log>` 追踪；串口只记录客户机实际输出，空日志不代表客户机健康，仍需结合 SSH、marker 与 EFI 证据。

2026-10-23 Fedora 43→44 UEFI 完整主场景通过，第二次 converge `ok=177 changed=0`、独立 verify `ok=7 changed=0`，已销毁测试 VM；日志 `/tmp/opencode/fedora-full-final.log`。恢复场景与覆盖边界见 `.scratch/upgrade-orchestration/execution.md`，无负载结果不推导生产安全。最终全仓 lint 通过、单测 70 项通过。

按清单 destroy 时，停机后先将 `serial.log`、`domain.xml`、`manifest.yml` 归档到 `${XDG_STATE_HOME:-$HOME/.local/state}/misaka-os-base/validation/<run_id>/<platform>/`，再删除磁盘等运行资源；可由 `driver.libvirt.libvirt_evidence_root` 指定持久证据根目录。目录 0700、文件 0600，归当前用户私有，不复制 SSH 私钥、seed 或磁盘。归档失败会停止清理。旧 `/tmp` 日志位置只反映历史测试，不保证仍存在，不恢复已丢失文件。串口可能含客户机敏感信息，对外分享前需检查。

## 本次实跑结果

| 场景 | syntax | create | converge | idempotence | verify | destroy |
|---|---|---|---|---|---|---|
| `docker`（Debian 12/13） | 通过 | 通过 | 通过 | 两台均 changed=0 | 通过，含服务启动与 docker info | 通过 |
| `podman_fedora`（Fedora 42） | 通过 | 通过 | 通过 | changed=0（ok=48） | 通过（ok=16），含 podman info | 通过 |

- 两个场景的 dependency 缺少 requirements 文件，cleanup/prepare/side_effect 缺少 playbook，按默认序列跳过，不代表对应测试通过。
- Docker 首次 verify 发现真实缺陷：drop-in 已写盘但未重载 systemd，仍使用厂商 `-H fd://`，与 daemon.json 的 `hosts` 冲突。现由 drop-in 变更通知 daemon-reload handler，仅重载单元，不启动或重启服务；完整重跑通过。
- Fedora 首次曾阻塞于 `Dockerfile.j2` 的 `dnf -y install systemd python3 sudo iproute procps-ng`，具体 URL 为 `https://mirrors.fedoraproject.org/metalink?repo=fedora-42&arch=x86_64`，dnf5 日志反复报 `Curl error (28): Timeout was reached`。原因是宿主 mihomo tproxy / br_netfilter 问题，现已修复；未为此修改角色、镜像源或断言。
- 网络恢复后的首次 Fedora 重跑暴露 verify 中两处循环缩进错误：`loop` / `loop_control` 误放在 `ansible.builtin.assert` 参数内，导致 `item` 未定义。已提升到任务层级，保留每个 drop-in 与 registry 配置文件存在的全部断言。随后完整 test 返回 0，Podman 版本为 5.8.2。
- 通过日志位于 `/tmp/opencode/containers-docker-retest.log`、`/tmp/opencode/containers-podman-fedora-final.log` 与 `/tmp/opencode/containers-lint.log`；Fedora 首次网络阻塞与 verify 缩进错误的日志分别保留在 `/tmp/opencode/containers-podman-fedora-test.log`、`/tmp/opencode/containers-fedora-build-dnf5.log` 与 `/tmp/opencode/containers-podman-fedora-retest.log`。

## 架构

- **驱动**：molecule `podman` 驱动（molecule-plugins 26.7.15），`systemd: always` 原生托管容器内 systemd
- **镜像**：自建 `Dockerfile.j2`（官方基础镜像 + systemd/python3 最小补集），不依赖第三方预制镜像
- **姊妹 collection**：`.dev/` symlink 树 + `ANSIBLE_COLLECTIONS_PATH`，直接消费工作区源码，无需 galaxy 拉取
- **验证策略**：容器道只断言 end-state（包装上、服务 enabled、配置渲染合法、幂等）；真实运行时行为（内核、PVE、dist-upgrade 重启链）留给 VM 道

| 场景 | 平台 | 路径 | 断言要点 |
|---|---|---|---|
| `docker` | Debian 12 (bookworm) + 13 (trixie) | docker-ce | 包齐、`docker` enabled、daemon.json 合法 JSON、drop-in 存在、显式 start 后 `docker info` 冒烟 |
| `podman_fedora` | Fedora 42 | podman + docker 模拟 | 包齐、docker 残留清干净、`podman-restart` enabled、`/run/docker.sock` 链接、nodocker 提示关闭、registries 配置渲染 |

分层矩阵（哪些能进容器道、哪些必须 VM）：

| 容器道 ✅ | 必须 VM ❌ |
|---|---|
| 镜像源、包安装、配置渲染、幂等 | pve_init / pve_on_debian（装的是虚拟化平台） |
| systemd 单元 enabled 状态 | dist-upgrade 双角色（需要 reboot） |
| docker/podman 安装 + enabled | sysctl 真实生效（容器里按设计跳过） |
| daemon.json / registries 配置 | btrfs 真实建文件系统 |

## 前置条件

```bash
# 安装与实际 Podman 驱动匹配的开发依赖（molecule-plugins[podman]）
uv sync

# 1. symlink 树（just molecule 会自动刷新，手动跑一次确认）
just dev-collections

# 2. 控制机 collection（已装：containers.podman 1.20.2 / community.docker 5.3.0）
uv run ansible-galaxy collection list | grep -E 'podman|docker'

# 3. 配置解析检查（不建容器，秒级）
cd collections/containers && uv run molecule list && cd -
```

## 执行测试

```bash
# containers 验收对应的 lint（当前 0 failure / 0 warning）
just lint containers

# Docker 场景（Debian 12/13；两台受管容器可能并行执行任务）
just molecule containers docker

# Podman 场景（Fedora 42）
just molecule containers podman_fedora
```

首次运行会拉基础镜像 + 构建 + 装包，**预计每个场景 5~15 分钟**（国内网络拉 `registry.fedoraproject.org` 无官方 mirror，可能更慢）。之后复用镜像缓存会快很多。

### molecule test 各阶段含义

| 阶段 | 做什么 | 失败时看什么 |
|---|---|---|
| `create` | podman build 自建镜像 + 起特权容器（systemd PID 1） | 镜像拉取网络、cgroup 权限 |
| `converge` | 跑 `misaka.containers.docker` playbook（含 os_base.auto_init 配源 → 装容器引擎） | 角色任务本身；国内镜像站连通性 |
| `idempotence` | **重跑 converge，必须 0 changed**（我们的核心设计约束） | 任何报 changed 的任务都是非幂等实锤，如实报 bug |
| `verify` | end-state 断言（见上表） | 断言消息直接指出哪个产物不对 |
| `destroy` | 清理容器 | — |

### 只想快速看某一步

```bash
cd collections/containers
export ANSIBLE_COLLECTIONS_PATH="$PWD/../../.dev:$ANSIBLE_COLLECTIONS_PATH"

uv run molecule create -s docker        # 只建容器
uv run molecule converge -s docker      # 只跑 playbook（可反复）
uv run molecule login -s docker -h docker-debian12   # 进容器人工检查
uv run molecule verify -s docker        # 只跑断言
uv run molecule destroy -s docker       # 清理
```

## 排障

| 症状 | 处理 |
|---|---|
| 拉镜像超时/慢 | Debian：确认 podman 有 docker.io mirror（`/etc/containers/registries.conf`）。Fedora：`registry.fedoraproject.org` 无国内 mirror，可临时换 `quay.io/fedora/fedora:42` |
| converge 卡在 apt/dnf | 多半是某个镜像站不通；`molecule login` 进容器手动 `apt update` 看哪个源挂了 |
| idempotence 报 changed | 看输出里标 changed 的任务名——那是角色的真实非幂等，别改测试迁就它，报给 orchestrator 修角色 |
| systemd 起不来（容器 Restarting） | 确认 `privileged: true` + `systemd: always` 都在；本机 cgroup 必须 v2（`stat -fc %T /sys/fs/cgroup` = `cgroup2fs`） |
| 残留清理 | `podman ps -a` 看容器；`podman images \| grep molecule` 看构建镜像；场景会自动 destroy，异常中断后手动 `molecule destroy -s <场景>` |

## 已知事项

- `daemon.json.j2` 的布尔渲染 bug（`True` 非法 JSON）已修复：`| bool | to_json`（CHANGELOG 1.2.0 有记录）。Docker 场景已移除字符串 workaround，显式传入原生布尔 `docker_enable_firewall: true`，并真实通过 JSON 校验与 daemon 启动。
- molecule 26.x 会提示 `WARNING Molecule scenarios should migrate to 'extensions/molecule'`——新版目录约定，暂不迁移，不影响运行。

## 后续扩展（未做）

- `os_base` 常规角色（debian_init / fedora_init / 镜像源）：直接复制本文档场景骨架，Dockerfile 换对应发行版，converge 改 import 对应 playbook
- CI：`molecule.yml` 的 `platforms.image` 可参数化 `"${MOLECULE_REGISTRY:-docker.io}/..."`，国内环境设 `MOLECULE_REGISTRY` 即可

## VM 道（非 Vagrant QEMU/KVM，UEFI）

2026-10-23 已在本机 libvirt 12.0.0 上跑通：

| 场景 | 结果 |
|---|---|
| `vm_smoke` Debian 13 Cloud | 通过。create / converge / idempotence / verify / destroy 均为 0。verify 确认 `/sys/firmware/efi` 是目录，并且 `/sys/firmware/efi/efivars` 里能列出 `Boot*` 变量。重启后 `boot_id` 变化。 |
| `vm_uefi_debian12` Debian 12 Cloud | 通过。同样的 EFI 变量证据。 |

两台 Debian 云镜像的测试没有获得 `bootctl` / `efibootmgr` 工具证据；未刷新 apt 索引直接安装 efibootmgr 曾报无候选，不能据此推断没有 apt 源。现有验收只直接读 EFI 变量目录，**不满足票 01 要求的工具证据全部条件**。域 XML 使用显式 pflash，NVRAM 是运行目录里的 `nvram.fd`。销毁用 `virsh destroy`，不使用 `undefine --nvram`。两次测试结束后宿主域仍只有 `openwrt` 和 `windows`，`default` 网络 UUID 仍是 `fa1d4afd-9482-40ab-9f31-ab1daa815496`。

Fedora 43 Generic 的 UEFI 与 43→44 升级后来已通过，历史结果见执行记录；不据此外推生产安全。

### local-manifest

与票 05 共用的文件是镜像路径加 `.manifest.yml`，例如 `debian-12.qcow2.manifest.yml`。摘要不符或 `uefi` 不是布尔 `true` 时拒绝启动。

```yaml
schema: 1
sha256: "<64 位小写十六进制>"
built_at: "2026-10-23T00:00:00Z"
source:
  iso: "<安装镜像文件名>"
  iso_sha256: "<64 位十六进制>"
os: debian
version: "12"
uefi: true
builder:
  name: packer
  template: debian
```

`source` 和 `builder` 必须是非空映射。解析器强制核对 `schema`、`sha256`、`built_at`、`os`、`version`、`uefi`。`source.iso_sha256` 建议填写，但解析器不替代 Packer 自己的安装镜像校验。

Packer 成品可保持私有权限。消费端校验原始摘要后，复制到临时缓存 `base/local-<sha256>.qcow2`（0444），再次核对缓存摘要，overlay 只写缓存之上的运行磁盘；不修改 Packer 原镜像、权限或 manifest。运行所有权清单用 `source_image` 记录原成品、`base_image` 记录实际 backing 文件。

跨仓真实集成入口（不构建、不升级系统；逐台运行）：

```bash
uv run python shared/scripts/validate_packer_libvirt.py \
  /path/to/packer/output/debian-uefi/debian-12.15-amd64.qcow2 \
  /path/to/packer/output/debian-uefi/debian-13.7-amd64.qcow2
```

入口在持久状态目录分配 `packer-libvirt-<UTC>-<pid>/`，保存 create/converge/idempotence/verify/destroy 日志、原始 manifest、域 XML、客户机重启前后事实、串口与 results.json。验证 q35/主仓当前 4M UEFI 固件、cloud-init SSH、Debian 身份、efibootmgr/EFI 变量、boot_id 改变和配置幂等，并在销毁后核对域清单、网络 UUID 与成品摘要不变。失败即停止，不继续启动下一台；恢复配置只记录路径，不归档私钥或 seed。若 create 尚未写清单即失败，需按持久 create.log、运行目录 XML 的 run_id/UUID 核对后处理，不能自动通配清理。

2026-10-23 实测：复用 Packer `dc1f2f2` 的 Debian 12.15、13.7 ISO 成品，逐台完整通过上述入口；两台第二次 converge 均 `ok=3 changed=0`，重启后仍可读 EFI 工具与变量、machine-id 保留、boot_id 改变，destroy 成功且源成品摘要未变。机器为 `pc-q35-10.2`，固件为 `/usr/share/edk2/ovmf/OVMF_CODE_4M.qcow2` 与 `OVMF_VARS_4M.qcow2`。证据：`~/.local/state/misaka-os-base/validation/packer-libvirt-20261023T152224Z-1227038/`。这是 Packer ISO 产物的跨固件消费证据，不替代前述 Debian Cloud 镜像工具证据缺口；未执行 Debian/PVE 升级。

Fedora 镜像来源是目录里的 `Fedora-Cloud-<版本>-<点版本>-x86_64-CHECKSUM`，不是固定文件名 `CHECKSUM`。只接受 `Fedora-Cloud-Base-Generic-<版本>-*.x86_64.qcow2`。

## VM 道（非 Vagrant QEMU/KVM）

容器道做不了的内核、重启链留在这里。历史基线是 Debian 13 SeaBIOS 冒烟；本轮迁移 `fedora_dist_upgrade` 并扩展 UEFI。`pve` 和旧的 `default` 脚手架没有迁移。旧模板 `shared/molecule/driver-template.yml` 仍是 Vagrant，新场景不要再复制它。

- **驱动**：Molecule 26 自管驱动 `driver.name: default` 且 `options.managed: true`。create/destroy 由场景 playbook 完成，成功后写 `instance_config.yml`（`instance` / `address` / `user` / `port` / `identity_file`）。
- **生命周期**：`shared/molecule/libvirt/`。`virsh` + `qemu-img` + `genisoimage`，不依赖 virt-install、cloud-localds 或 Python libvirt。
- **镜像**：create 时读取 `https://cloud.debian.org/images/cloud/trixie/latest/` 的目录索引和 `SHA512SUMS`，只接受文件名匹配 `^debian-13-generic-amd64[.]qcow2$$` 的唯一条目。Molecule 用 `string.Template`，`$` 必须写成 `$$`，点号用字符类，不能写 `\.`。基镜像缓存在 `/tmp/opencode/misaka-molecule-libvirt/base/`，校验通过后 `0444`。每次运行用独立 overlay，不把磁盘放进 libvirt default 存储池。
- **来宾**：NoCloud seed（`genisoimage -volid cidata`）+ 本次运行专用 ed25519 key + `molecule` 用户。网络只用已经活跃的 `qemu:///system` `default` NAT，不执行 `net-define` / `net-start` / `net-destroy` / reload，不改宿主路由、sysctl 或已有虚拟机。libvirt 启动域时自己可能添加防火墙规则，不能说成零网络规则变更。
- **销毁**：只处理当前 `instance_config.yml` 点名、且 manifest 与域 metadata 标记一致的瞬态域。删除范围只有该清单里的 overlay、seed 和实例目录。禁止 `undefine --remove-all-storage`、通配删除和清理宿主原有域。基镜像不删。

```bash
cd collections/os_base
export ANSIBLE_COLLECTIONS_PATH="$PWD/../../.dev:${ANSIBLE_COLLECTIONS_PATH:-}"
uv run molecule test -s vm_smoke
```

`vm_smoke` 序列：syntax → destroy → create → converge（写 `/etc/misaka-molecule/vm-smoke`）→ idempotence（必须 0 changed）→ verify（SSH、Debian 13、kvm guest、仅在 verify 中 reboot，并检查 `/proc/sys/kernel/random/boot_id` 前后不同）→ destroy。

首次会下载约 400MB 官方 qcow2。访问 `qemu:///system` 或 default 网络失败时 create 直接失败，不要为了跑通去改权限、SELinux 或共享目录。
