### PZT 精选插件-开始
zi lucid wait for \
    depth=1 \
    multisrc"modules/archive/*.zsh" \
    pick"/dev/null" \
    from"{{ choose_github_mirror() }}" \
    sorin-ionescu/prezto

zi lucid wait for \
    depth=1 \
    multisrc"modules/utility/*.zsh" \
    pick"/dev/null" \
    from"{{ choose_github_mirror() }}" \
    sorin-ionescu/prezto

zi lucid wait for \
    depth=1 \
    multisrc"modules/directory/*.zsh" \
    pick"/dev/null" \
    from"{{ choose_github_mirror() }}" \
    sorin-ionescu/prezto

zi lucid wait has"dnf" for \
    depth=1 \
    multisrc"modules/dnf/*.zsh" \
    pick"/dev/null" \
    from"{{ choose_github_mirror() }}" \
    sorin-ionescu/prezto

zi lucid wait has"yum" for \
    depth=1 \
    multisrc"modules/yum/*.zsh" \
    pick"/dev/null" \
    from"{{ choose_github_mirror() }}" \
    sorin-ionescu/prezto

zi lucid wait has"dpkg" for \
    depth=1 \
    multisrc"modules/dpkg/*.zsh" \
    pick"/dev/null" \
    from"{{ choose_github_mirror() }}" \
    sorin-ionescu/prezto
### PZT 精选插件-结束
