# misaka.uv

声明式管理 `uv tool` 安装的用户级 Python CLI。不属于 OS 初始化，因此独立于 `misaka.os_base`。

uv 本身没有官方工具清单；本 collection 用 Ansible 变量补上这一层。单工具幂等仍由 `uv tool install` 的 receipt 保证。

## 快速开始

```bash
./local_install.sh
```

设备侧 playbook 引用 `misaka.uv.tools`，清单放在调用方（例如 `gzz-devices`），不要写进 role 默认值。

## Role

- [`tools`](roles/tools/) — 按 `tools_list` 清单安装 / 可选升级
