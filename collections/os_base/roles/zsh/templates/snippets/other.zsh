### 一些杂项-开始

# hugo 静态网站生成工具
zi lucid wait'1' has"hugo" for \
    id-as"hugo_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"hugo gen autocomplete -t zsh > _hugo; zi creinstall -q hugo_completion" \
    atpull"%atclone" \
    run-atpull \
    nocompile \
    z-shell/null

# Navi 速查表工具
# zi lucid wait has"navi" for \
#     id-as"hugo-completion" \
#     as"completion" \
#     atclone"navi widget zsh > _navi" \
#     atpull"%atclone" \
#     run-atpull \
#         z-shell/null
# 检测 navi 命令是否存在
# if [ -x "$(command -v navi)" ]; then
#     eval "$(navi widget zsh)"
# fi

# Just 快速命令工具
zi lucid wait'1' has"just" for \
    id-as"just_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"just --completions zsh > _just; zi creinstall -q just_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null

# if [ -x "$(command -v navi)" ]; then
#     alias j=just
#     alias .j='just --justfile ~/.user.justfile --working-directory .'
# fi

# CoSign 通用签名工具
zi lucid wait'1' has"cosign" for \
    id-as"cosign_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"cosign completion zsh > _cosign; zi creinstall -q cosign_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null

# task 任务管理工具
zi lucid wait'1' has"task" for \
    id-as"task_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"just --completions zsh > _just; zi creinstall -q just_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null

# tailscale 内网穿透
zi lucid wait'1' has"tailscale" for \
    id-as"tailscale_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"tailscale completion zsh > _tailscale; zi creinstall -q tailscale_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null

# rclone 多云存储管理工具
zi lucid wait'1' has"rclone" for \
    id-as"rclone_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"rclone completion zsh - > _rclone; zi creinstall -q rclone_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null

# yq 多种配置的解析工具, jq 强化
zi lucid wait'1' has"yq" for \
    id-as"yq_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"yq completion zsh > _yq; zi creinstall -q yq_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null

# cue 一种配置语言
zi lucid wait'1' has"cue" for \
    id-as"cue_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"cue completion -s zsh > _cue; zi creinstall -q cue_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null

# Jira CLI
zi lucid wait'1' has"jira" for \
    id-as"jira_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"jira completion zsh > _jira; zi creinstall -q jira_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null


zi lucid wait'1' has"tofu" for \
    atload"zicompinit; zicdreplay" \
    multisrc"plugins/opentofu/*.zsh" \
    pick"/dev/null" \
    from"{{ choose_github_mirror() }}" \
    ohmyzsh/ohmyzsh

# Terragrunt 跟 Tofu/Terraform 一个框架出的,所以特殊一点
# OpenTofu/Terraform 也可以使用这个办法来添加补全
zi lucid wait'1' has"terragrunt" for \
    id-as"terragrunt_completion" \
    as"completion" \
    atload"zicompinit; zicdreplay" \
    atclone"complete -o nospace -C terragrunt terragrunt" \
    atpull"%atclone" \
    run-atpull \
    from"{{ choose_github_mirror() }}" \
    z-shell/null

zi lucid wait'1' has"limactl" for \
    id-as"limactl_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"limactl completion zsh > _limactl; zi creinstall -q limactl_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null

# incus LXD 出的新管理工具
zi lucid wait'1' has"incus" for \
    id-as"incus_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"incus completion zsh > _incus; zi creinstall -q incus_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null

### 一些杂项-结束
