# ZSH

下面列举一下我的 Shell 进化史

- 第 1 代 bash
- 第 2 代 zsh
- 第 3 代 omz
- 第 4 代 omz 和他的插件们
- 第 5 代 byobu
- 第 6 代 zinit 和 omz
- 第 8 代 zinit 延迟加载
- 第 9 代 p10k 主题
- 第 10 代 抛弃加载整个 OMZ
- 第 11 代 fzf
- 第 12 代 loki-shell
- 第 13 代 fzf-tab
- 第 14 代 非 snippet 加载 OMZ 插件
- 第 15 代 从命令输出加载补全
- 第 16 代 nodejs 条件加载优化
- 第 17 代 现代化 Shell 工具，不单单是 fzf
- 第 18 代 asdf 版本管理，替代 nvm 和 rvm
- 第 19 代 Volta.sh 管理 nvm 版本
- 第 20 代 切换到全新的 zinit 继任者 zi.dev
- 第 21 代 使用 zshell 提供的各种语法糖
- 第 22 代 评估 PZT 但是还是选择了 OMZ
- 第 23 代 docker 家族补全优化
- 第 24 代 K8S Krew 插件的补全支持
- 第 25 代 使用 fnm 代替没啥存在感的 Volta.sh
- 第 26 代 取消 SDKMAN 下载劫持，因为官方换到 Rust 写的 CLI
- 第 27 代 引入 nix 和 home-manager 作为第三方包补充
- 第 28 代 go node 等基础语言版本交给 nix 管理
- 第 29 代 引入 direnv 环境管理，与 nix 是绝配
- 第 30 代 引入现代化 Python 工具补全支持，uv pixi manba hatch 等

目前选择的现代化 Shell 工具有

- fzf 模糊搜索
- fd 文件搜索
- exa 文件列表
- dust 文件大小列表
- tokei 源代码分析
- duf 文件大小列表
- broot 文件树
- gping 可视化 Ping
- delta Git 文件差异
- procs 可视化进程管理
- dive Docker 镜像分析
-
- q DNS 客户端 [这里](https://github.com/natesales/q)

处于更新和版本问题，只有以下工具安装于服务器

- fzf
- exa (已弃用，交给 LSD)
- lsd

于第 18 代加入

- navi 速查表

## ASDF 版本管理

单独使用一个片段来管理 ASDF . 包括安装 ASDF 插件等

而各语言各自的片段则放置与该语言相关工具的东西

## 镜像与加速配置

当目标主机环境需要加速时（如 `host_geo.country == 'cn'`），可通过变量指定用于 zi 插件拉取的 GitHub / GitLab 代理或镜像端点。默认留空，具备空安全保护，留空时自动回退为官方直连地址（`github.com` / `gitlab.com`）。

| 变量名 | 默认值 | 说明 |
|---|---|---|
| `zsh_github_repo_mirror_cn` | `""` | 国内 GitHub 镜像或代理（如 `hub.example.com` 或 `ghproxy.example.com/https://github.com`） |
| `zsh_gitlab_repo_mirror_cn` | `""` | 国内 GitLab 镜像或代理（如 `gitlab-mirror.example.com`） |
| `zsh_force_remove_zi` | `false` | 是否强制清理旧插件以触发重新初始化 |

### 示例配置

```yaml
zsh_github_repo_mirror_cn: "hub.example.com"
zsh_gitlab_repo_mirror_cn: "gitlab-mirror.example.com"
```
