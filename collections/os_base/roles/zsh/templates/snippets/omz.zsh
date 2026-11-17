### OMZ 精选插件-开始

# 加载 thefuck
zi lucid wait'1' has"thefuck" for \
    multisrc"plugins/thefuck/*.zsh" \
    pick"/dev/null" \
    from"{{ choose_github_mirror() }}" \
    ohmyzsh/ohmyzsh



# 加载 sudo
zi lucid wait'1' has"sudo" for \
    multisrc"plugins/sudo/*.zsh" \
    pick"/dev/null" \
    from"{{ choose_github_mirror() }}" \
    ohmyzsh/ohmyzsh

# 加载 colored-man-pages
zi lucid wait'1' has"man" for \
    multisrc"plugins/colored-man-pages/*.zsh" \
    pick"/dev/null" \
    from"{{ choose_github_mirror() }}" \
    ohmyzsh/ohmyzsh

# 加载 autojump
zi lucid wait'1' has"autojump" for \
    multisrc"plugins/autojump/*.zsh" \
    pick"/dev/null" \
    from"{{ choose_github_mirror() }}" \
    ohmyzsh/ohmyzsh

# 加载 command-not-found
zi lucid wait'1' for \
    multisrc"plugins/command-not-found/*.zsh" \
    pick"/dev/null" \
    from"{{ choose_github_mirror() }}" \
    ohmyzsh/ohmyzsh

# 解压插件
# zi lucid wait'1' for \
#     multisrc"plugins/extract/*.zsh" \
#     pick"/dev/null" \
#     from"{{ choose_github_mirror() }}" \
#     ohmyzsh/ohmyzsh

# Homebrew
# zi lucid wait'1' has"brew" for \
#     multisrc"plugins/brew/*.zsh" \
#     pick"/dev/null" \
#     from"{{ choose_github_mirror() }}" \
#     ohmyzsh/ohmyzsh

### OMZ 精选插件-结束
