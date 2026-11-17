### Python-开始
# 加载 pip
zi lucid wait'1' has"pip" for \
    multisrc"plugins/pip/*.zsh" \
    pick"/dev/null" \
    from"{{ choose_github_mirror() }}" \
    ohmyzsh/ohmyzsh \
    as"completion" \
    multisrc"plugins/pip/_*" \
    pick"/dev/null" \
    from"{{ choose_github_mirror() }}" \
    ohmyzsh/ohmyzsh

# 加载 pipx
zi lucid wait'1' has"pipx" for \
    id-as"pipx_completion" \
    if'[ -x "$(command -v register-python-argcomplete)" ]' \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"register-python-argcomplete -s zsh pipx > _pipx; zi creinstall -q pipx_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null

# 加载 poetry
export ZSH_POETRY_AUTO_ACTIVATE=0
export ZSH_POETRY_AUTO_DEACTIVATE=0
zi lucid wait'1' has"poetry" for \
    from"{{ choose_github_mirror() }}" \
    darvid/zsh-poetry

# 加载 poetry 但是来自 omz 的插件
zi lucid wait'1' has"poetry" for \
    multisrc"plugins/poetry/*.zsh" \
    pick"/dev/null" \
    from"{{ choose_github_mirror() }}" \
    ohmyzsh/ohmyzsh

# 加载 conda
zi lucid wait'1' has"conda" for \
    multisrc"plugins/conda/*.zsh" \
    pick"/dev/null" \
    from"{{ choose_github_mirror() }}" \
    ohmyzsh/ohmyzsh

# 加载 pixi
zi lucid wait'1' has"pixi" for \
    id-as"pixi_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"pixi completion --shell zsh > _pixi; zi creinstall -q pixi_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null

# 加载 uv
# 先是 uv 的 omz 插件
zi lucid wait'1' has"uv" for \
    multisrc"plugins/uv/*.zsh" \
    pick"/dev/null" \
    from"{{ choose_github_mirror() }}" \
    ohmyzsh/ohmyzsh

# 然后单独管理补全
zi lucid wait'1' has"uv" for \
    id-as"uv_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"uv generate-shell-completion zsh > _uv; zi creinstall -q uv_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null
### Python-结束
