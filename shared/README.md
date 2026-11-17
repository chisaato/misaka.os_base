# shared/ — 共享基础设施

本仓库是 monorepo 结构，包含三个 Ansible Collection：

- `collections/os_base/` → `misaka.os_base`
- `collections/containers/` → `misaka.containers`
- `collections/uv/` → `misaka.uv`

`shared/` 目录存放三个 collection 共用的基础设施：

## 目录说明

| 路径 | 用途 |
|------|------|
| `shared/molecule/` | Molecule 测试参考配置片段 |
| `shared/scripts/` | 开发用 collection symlink 树等共享辅助脚本 |
| `shared/TESTING.md` | 容器道与 VM 道的实跑状态、执行方式与排障 |

## molecule 测试指南

Collection 各自维护独立的 molecule 场景（在各自 `molecule/` 下），共用根目录工具链与本地 collection 解析：

- **Driver**: `containers` 双场景使用 Podman + 自建 systemd 镜像。`os_base` 的 VM 冒烟使用 Molecule 26 自管驱动（`driver.name: default`）加 `shared/molecule/libvirt/` 的 QEMU/KVM 生命周期，不再走 Vagrant。旧的 `shared/molecule/driver-template.yml` 只留作尚未迁移的 Vagrant 场景参考。
- **Lint**: 根目录的 `.ansible-lint` 统一控制

运行测试：

```bash
# os_base 场景
just molecule os_base auto_init
just molecule os_base debian_init

# os_base VM 冒烟（Debian 13，qemu:///system 上已有的 default NAT）
just molecule os_base vm_smoke

# containers 场景
just molecule containers docker
just molecule containers podman_fedora
```

> `just molecule` 会刷新 `.dev/ansible_collections` symlink 树并设置 `ANSIBLE_COLLECTIONS_PATH`，直接消费工作区源码。手动运行时需先执行 `just dev-collections`，在对应 collection 目录下通过 `uv run molecule` 执行。
