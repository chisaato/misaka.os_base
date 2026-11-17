### PHP-开始

# 加载 DDEV
zi lucid wait'1' has"ddev" for \
    id-as"ddev_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"ddev completion zsh > _ddev; zi creinstall -q ddev_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null
### PHP-结束
