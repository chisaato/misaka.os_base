### 容器部分-开始

# 来自 Docker 官方的补全
# 测试对 docker compose 也有效
zi lucid wait'1' has"docker" for \
    id-as"docker_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"docker completion zsh > _docker; zi creinstall -q docker_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null

# 允许对堆叠进行补全
zstyle ':completion:*:*:docker:*' option-stacking yes
zstyle ':completion:*:*:docker-*:*' option-stacking yes


# 加载 OMZ docker-compose 插件
zi lucid wait'1' has"docker" for \
    multisrc"plugins/docker-compose/*.zsh" \
    pick"/dev/null" \
    from"{{ choose_github_mirror() }}" \
    ohmyzsh/ohmyzsh
### 容器部分-结束
