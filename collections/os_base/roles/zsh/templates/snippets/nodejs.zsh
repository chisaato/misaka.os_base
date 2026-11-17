### NodeJS-开始
# Yarn
# 但是不加载 Yarn 的补全
# zi lucid wait'1' for \
#     wait'[[ $(command -v yarn) ]]' \
#     multisrc"plugins/yarn/*.zsh" \
#     pick"/dev/null" \
#     from"{{ choose_github_mirror() }}" \
#     ohmyzsh/ohmyzsh

# Yarn自动完成
# zi lucid wait"1" for \
#     wait'[[ $(command -v yarn) ]]' \
#     depth"1" \
#     atload"zpcdreplay" \
#     atclone'./zplug.zsh' \
#     from"{{ choose_github_mirror() }}" \
#     g-plane/zsh-yarn-autocompletions

# Volta
zi lucid for \
    if'[ -s "$HOME/.volta" ]' \
    depth"1" \
    from"{{ choose_github_mirror() }}" \
    cowboyd/zsh-volta

zi lucid wait'1' has"volta" for \
    id-as"volta_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"volta completions zsh > _volta; zi creinstall -q volta_completion" \
    atpull"%atclone" \
    run-atpull \
    nocompile \
    z-shell/null
# fnm 另一个社区主推的管理工具
zi lucid wait'1' has"fnm" for \
    id-as"fnm_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"fnm completions --shell zsh > _fnm; zi creinstall -q fnm_completion" \
    atpull"%atclone" \
    run-atpull \
    nocompile \
    z-shell/null
zi lucid wait'1' has"fnm" for \
    depth"1" \
    from"{{ choose_github_mirror() }}" \
    dominik-schwabe/zsh-fnm
### NodeJS-结束
