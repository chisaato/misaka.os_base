### Go-开始

# redress Go 逆向工具
zi lucid wait'1' has"redress" for \
    id-as"redress_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"redress completion zsh > _redress; zi creinstall -q redress_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null

# ko Go 容器构建工具
zi lucid wait'1' has"ko" for \
    id-as"ko_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"ko completion zsh > _ko; zi creinstall -q ko_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null
### Go-结束
