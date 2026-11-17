### Shell 辅助工具-开始

# chezmoi dotfiles 管理工具
zi lucid wait'1' has"chezmoi" for \
    id-as"chezmoi_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"chezmoi completion zsh > _chezmoi; zi creinstall -q chezmoi_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null

# proto 单一的工具版本管理器
zi lucid wait'1' has"proto" for \
    id-as"proto_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"proto completions --shell zsh > _proto; zi creinstall -q proto_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null

# ziti OpenZiti 安全访问
zi lucid wait'1' has"ziti" for \
    id-as"ziti_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"ziti completion zsh > _ziti; zi creinstall -q ziti_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null

# step Step CA 证书管理工具
zi lucid wait'1' has"step" for \
    id-as"step_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"step completion zsh > _step; zi creinstall -q step_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null

# flatpak 跨发行版的包管理器
zi lucid wait'1' has"flatpak" for \
    id-as"flatpak_completion" \
    as"completion" \
    https://{{ choose_github_mirror() }}/flatpak/flatpak/raw/refs/heads/main/completion/_flatpak

# direnv 环境变量管理工具
zi lucid wait'1' has"direnv" for \
    id-as"direnv_hook" \
    from"{{ choose_github_mirror() }}" \
    atclone"direnv hook zsh > zhook.zsh" \
    atpull'%atclone' \
    src="zhook.zsh" \
    z-shell/null
# nix 官方补全
zi lucid wait'1' has"nix" for \
    id-as"nix_completion" \
    from"{{ choose_github_mirror() }}" \
    nix-community/nix-zsh-completions
### Shell 辅助工具-结束