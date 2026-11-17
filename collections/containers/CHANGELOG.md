# Changelog

## Unreleased

- 修复 Docker systemd drop-in 写盘后未重载单元的问题：变更时通知 daemon-reload handler，避免厂商 `-H fd://` 与 daemon.json `hosts` 冲突；不启动或重启 Docker。
- Docker Molecule 场景改用原生布尔配置；Debian 12/13 与 Fedora 42 全流程实跑通过，幂等均为 0 changed。
- 修复 Fedora Molecule verify 中 drop-in 与 registry 配置文件断言的循环缩进，避免 `item` 未定义；保留全部逐文件断言。

## 1.2.0

- docker 角色：Docker CE / Podman 安装与配置；服务仅做开机自启（enabled），绝不在运行中重启
- daemon.json 改用 `ansible.builtin.template` 渲染并加 JSON 校验；Docker CE keyring 先探测后导入
- 修复 daemon.json.j2 将 `docker_enable_firewall`（YAML 布尔）渲染为 `True` 导致 JSON 校验失败的问题，现统一经 `| bool | to_json` 输出 JSON 字面量
- Playbook 角色引用改用 FQCN；显式声明依赖 `misaka.os_base >=1.12.0`
- 清理死代码与未使用变量；变量统一 `docker_` 前缀
