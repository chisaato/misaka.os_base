### 初始部分-开始

# Code Stats 统计插件
# 已启用条件加载
zi lucid wait'1' for \
    depth"1" \
    if'[ ! -z ${CODESTATS_API_KEY} ]' \
    from"gitlab.com" \
    code-stats/code-stats-zsh

zi lucid wait'1' for \
    from"{{ choose_github_mirror() }}" \
    z-shell/zui

# fzf 补全和绑定
zi lucid wait'1' has"fzf" for \
    depth"1" \
    multisrc"plugins/fzf/*.zsh" \
    pick"/dev/null" \
    from"{{ choose_github_mirror() }}" \
    ohmyzsh/ohmyzsh

# OMZ 框架
necessary_omz_libs=(
    lib/completion.zsh
    lib/history.zsh
    lib/key-bindings.zsh
    lib/theme-and-appearance.zsh
    lib/directories.zsh
    lib/functions.zsh
    lib/git.zsh
    lib/grep.zsh
    lib/compfix.zsh
    lib/termsupport.zsh
    lib/nvm.zsh
    lib/misc.zsh
)

zi lucid for \
    depth"1" \
    multisrc"$necessary_omz_libs" \
    pick"/dev/null" \
    from"{{ choose_github_mirror() }}" \
    ohmyzsh/ohmyzsh

# fzf-tab fzf 增强
zi wait'1' lucid has"fzf" for \
    depth"1" \
    from"{{ choose_github_mirror() }}" \
    Aloxaf/fzf-tab

# fzf 额外配置
# 列出目录
# 如果有 exa 则用 exa
if command -v exa &>/dev/null; then
    zstyle ':fzf-tab:complete:cd:*' fzf-preview 'exa -1 --color=always $realpath'
elif command -v eza &>/dev/null; then
    zstyle ':fzf-tab:complete:cd:*' fzf-preview 'eza -1 --color=always $realpath'
elif command -v lsd &>/dev/null; then
    zstyle ':fzf-tab:complete:cd:*' fzf-preview 'lsd -1 --color=always $realpath'
else
    zstyle ':fzf-tab:complete:cd:*' fzf-preview 'ls -1 --color=always $realpath'
fi
# 显示 Systemd 服务状态
zstyle ':fzf-tab:complete:systemctl-*:*' fzf-preview 'SYSTEMD_COLORS=1 systemctl status $word'

# 对 kill 命令进行提示
zstyle ':completion:*:*:*:*:processes' command "ps -u $USER -o pid,user,comm -w -w"
zstyle ':fzf-tab:complete:(kill|ps):argument-rest' fzf-preview \
    '[[ $group == "[process ID]" ]] && ps --pid=$word -o cmd --no-headers -w -w'
zstyle ':fzf-tab:complete:(kill|ps):argument-rest' fzf-flags --preview-window=down:3:wrap

# 环境变量显示
zstyle ':fzf-tab:complete:(-command-|-parameter-|-brace-parameter-|export|unset|expand):*' \
	fzf-preview 'echo ${(P)word}'


# 按照文档指示的最一键用法
# zi lucid for light-mode \
#     depth"1" \
#     from"{{ choose_github_mirror() }}" \
#     @zsh-users+fast

# 三合一用法
# zi wait lucid for \
#     atinit"ZI[COMPINIT_OPTS]=-C; zicompinit; zicdreplay" \
#     atpull"cp share/free_theme.zsh ${FAST_WORK_DIR:-${XDG_CACHE_HOME:-~/.cache}/f-sy-h}/secondary_theme.zsh" \
#     atload'fsh_theme default &>/dev/null;' \
#     run-atpull \
#     from"{{ choose_github_mirror() }}" \
#         z-shell/F-Sy-H \
#     blockf \
#     from"{{ choose_github_mirror() }}" \
#         zsh-users/zsh-completions \
#     atload"!_zsh_autosuggest_start" \
#     from"{{ choose_github_mirror() }}" \
#         zsh-users/zsh-autosuggestions

# 早期传统加载法,适合需要自定义的
zi wait'1' lucid for \
    depth"1" \
    from"{{ choose_github_mirror() }}" \
    atload"_zsh_autosuggest_start" \
    zsh-users/zsh-autosuggestions

# # 另一款比较好看的主题是 free 其他都一般般
export FAST_THEME_NAME="default"
zi wait'1' lucid for \
    depth=1 \
    from"{{ choose_github_mirror() }}" \
    atclone'git checkout v1.67' \
    atinit"ZI[COMPINIT_OPTS]=-C; zicompinit; zicdreplay" \
    atpull"git checkout v1.67 && cp share/free_theme.zsh ${FAST_WORK_DIR:-${XDG_CACHE_HOME:-~/.cache}/f-sy-h}/secondary_theme.zsh" \
    atload'fast-theme default &>/dev/null;' \
    ver'v1.67' \
    run-atpull \
    z-shell/F-Sy-H

zi wait'1' lucid for \
    depth"1" \
    from"{{ choose_github_mirror() }}" \
    atpull'zi creinstall -q .' \
    pick'/dev/null' \
    blockf \
    zsh-users/zsh-completions

# atinit'AUTOCD=1' 可以在进入目录时自动列出文件
zi lucid wait'1' has'exa' for \
    depth"1" \
    from"{{ choose_github_mirror() }}" \
    zplugin/zsh-exa

# eza 的补全
# 先加载补全
zi lucid wait'1' has"eza" for \
    id-as"eza_completion" \
    as"completion" \
    https://{{ choose_github_mirror() }}/eza-community/eza/raw/refs/heads/main/completions/zsh/_eza

# 对于较新的系统应当加载 eza
zi lucid wait'1' has'eza' for \
    depth"1" \
    from"{{ choose_github_mirror() }}" \
    z-shell/zsh-eza

# Fedora 42 移除了 eza 现在改用 lsd
zi lucid wait'1' has'lsd' for \
    depth"1" \
    from"{{ choose_github_mirror() }}" \
    z-shell/zsh-lsd

# zoxide 快速目录跳转
# zi 缩写有冲突,要用 z-shell 维护的版本
zi lucid wait'1' has"zoxide" for \
    depth"1" \
    from"{{ choose_github_mirror() }}" \
    atclone"git submodule set-url zoxide https://{{ choose_github_mirror() }}/ajeetdsouza/zoxide" \
    z-shell/zsh-zoxide

zi wait'1' lucid for \
    depth"1" \
    from"{{ choose_github_mirror() }}" \
    z-shell/zi-console

zi wait'1' lucid for \
    depth"1" \
    from"{{ choose_github_mirror() }}" \
    MichaelAquilina/zsh-you-should-use

### 初始部分-结束
