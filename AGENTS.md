# misaka.os_base — Ansible Collection Monorepo

## 项目身份

- **仓库**: 包含三个 Ansible Collection 的 monorepo
  - `misaka.os_base` — 操作系统基础初始化（镜像源、系统配置、PVE 等）
  - `misaka.containers` — 容器环境安装（Docker、Podman）
  - `misaka.uv` — uv 与 uv tools 管理
- **namespace**: `misaka`
- **最低 Ansible 版本**: `>=2.15.0`
- **支持系统**: Debian 最新 2 个版本、Fedora 最新 2 个版本、AlmaLinux 9、Proxmox VE

## 仓库布局

```
collections/
├── os_base/                          ← misaka.os_base
│   ├── galaxy.yml
│   ├── meta/runtime.yml
│   ├── roles/         (16 个角色)
│   ├── playbooks/     (9 个入口)
│   ├── plugins/
│   ├── molecule/      (6 个场景)
│   └── tests/unit/
├── containers/                       ← misaka.containers
│   ├── galaxy.yml
│   ├── meta/runtime.yml
│   ├── roles/         (docker 角色)
│   ├── playbooks/     (2 个入口)
│   ├── plugins/
│   └── molecule/      (2 个场景)
└── uv/                               ← misaka.uv
    ├── galaxy.yml
    ├── meta/runtime.yml
    ├── roles/         (tools 角色)
    ├── playbooks/     (1 个入口)
    └── plugins/
shared/                               ← 共享基础设施
├── molecule/
├── scripts/
└── README.md
```

## 核心命令

```bash
# 构建并安装全部 Collection（产物在仓库根目录）
just
# 或者
just all

# 构建 Collection（支持指定名称，如 just build uv）
just build
just build os_base
just build containers
just build uv

# 安装 Collection（产物为 misaka-{name}-{version}.tar.gz）
just install
just install os_base
just install containers
just install uv

# 清理根目录构建产物
just clean
```

## 测试与验证流程

### 1. Lint 检查（根目录 `.ansible-lint` 统一控制）

```bash
just lint
just lint os_base
just lint containers
just lint uv
```

### 2. 单元测试（pytest）

```bash
just test-unit
# 等价于: uv run pytest collections/os_base/tests/unit/
```

### 3. Molecule 集成测试

执行前会自动调用 `just dev-collections`（刷新 `.dev/` 下的本地 collection symlink 树并设置 `ANSIBLE_COLLECTIONS_PATH`）：

```bash
# 运行指定 Collection 的 Molecule 场景
just molecule <collection> <scenario>
# 示例：
just molecule containers docker
just molecule containers podman_fedora
```

> 说明：部分重型集成场景（如跨大版本升级、PVE 实验室等）依赖本地 libvirt/QEMU 虚拟化环境与 `shared/molecule/` 下的镜像构建，在无虚拟化支持的容器或 CI 环境中无法直接运行。

## 发布流程

1. **版本与变更日志**：更新对应 `collections/<name>/galaxy.yml` 中的 `version` 字段，并在 `collections/<name>/CHANGELOG.md` 中记录变更。
2. **元数据核对**：确认 `galaxy.yml` 的 `repository`、`issues` 与 `dependencies` 已正确填写。
3. **发布前验证**：
   ```bash
   just lint
   just test-unit
   # 按需执行受影响角色的 Molecule 场景
   ```
4. **构建安装包**：
   ```bash
   just clean
   just build <name>   # 生成 misaka-<name>-<version>.tar.gz
   ```
5. **推送双远端与 Tag**：
   - 打上版本标签并推送至 GitHub 与 GitLab 远端。
6. **发布至 Ansible Galaxy**：
   ```bash
   uv run ansible-galaxy collection publish misaka-<name>-<version>.tar.gz --api-key <ANSIBLE_GALAXY_TOKEN>
   ```

## 构建产物

- `misaka-os_base-<version>.tar.gz` / `misaka-containers-<version>.tar.gz` / `misaka-uv-<version>.tar.gz`
- 被 `.gitignore` 排除
- 构建前需确认各自 `galaxy.yml` 中 `version` 已更新

## 共享基础设施

三个 collection 共用：
- `.ansible-lint` — 统一的 lint 规则（跳过 `name[template]`；`var-naming[no-role-prefix]` 已启用，角色内 set_fact/register/defaults 变量必须带角色名前缀）
- `shared/` — molecule 模板、辅助脚本

## 设计约束

- 所有 Playbook/role 设计原则是**幂等**，且变更上报必须诚实：写操作先探测后执行，禁止用 `changed_when: false` 掩盖
- China-First 设计：默认按国内镜像处理；不要散写 `host_geo.country` 判断，各角色开头派生 `<role>_use_cn_mirror`（`(host_geo.country | default('cn')) == 'cn'`），任务与模板统一消费该变量
- 长任务（包安装、下载）使用 `retries` + `until` 抗网络抖动；不使用 `async: 0` / `poll`
- 模块一律 FQCN；版本比较一律 `| int`
- 发行版专用角色：main 主体包 `block:` + `when: ansible_facts['distribution'] == '<Distro>'` 守卫，不匹配时 debug 提示并跳过
- 跨版本渲染契约（dist-upgrade 角色经 `include_role` + `vars` 覆写，禁止覆写 `ansible_facts`）：
  - `debian_repo_target_codename` / `debian_repo_target_major_version`
  - `fedora_repo_target_major_version`
- 详细的设计决策（Debian 版本分支、Fedora 版本分支、角色依赖链等）见各自 Collection 内的历史文档

## Agent skills

### Issue tracker

Issues 与 spec 以本地 Markdown 存放在 `.scratch/<feature>/`。See `docs/agents/issue-tracker.md`.

### Triage labels

使用默认五个 triage 角色标签（`needs-triage` / `needs-info` / `ready-for-agent` / `ready-for-human` / `wontfix`）。See `docs/agents/triage-labels.md`.

### Domain docs

Single-context：根目录 `GLOSSARY.md` + `docs/adr/`（按需惰性创建）。See `docs/agents/domain.md`.
