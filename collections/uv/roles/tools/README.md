# misaka.uv.tools

按清单调用 `uv tool install`。单工具幂等由 uv receipt 保证（含 `--with`）。

## 变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `tools_list` | `[]` | 工具清单，见下方形状 |
| `tools_state` | `present` | `present` 或 `latest` |
| `tools_bin` | `""` | uv 绝对路径；空则自动查找 |
| `tools_executable` | `uv` | 查找用的命令名 |

清单项：

```yaml
tools_list:
  - name: ansible
    with: [kubernetes, helm, jmespath]
    with_executables_from: [ansible-core]
  - name: ida-pro-mcp
    source: https://github.com/mrexodia/ida-pro-mcp/archive/refs/heads/main.zip
    with: [tomli-w, idapro]
  - name: basedpyright
```

- `name` 必填，也是 `uv tool upgrade` 用的包名
- `source` 可选，git/URL/路径；缺省则安装 `name`
- `force` / `python` / `state` 可按项覆盖

不卸载清单外的工具。以 `ansible_user` 的家目录安装，不要对 root 跑除非你就是要装给 root。
