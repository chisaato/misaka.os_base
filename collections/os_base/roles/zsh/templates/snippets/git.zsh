### Git-开始

# 加载 Git 插件

# git 的补全
zi lucid wait'1' has"git" for \
    id-as"git_completion" \
    as"completion" \
    https://{{ choose_github_mirror() }}/git/git/raw/refs/heads/master/contrib/completion/git-completion.zsh

# GitIgnore
zi lucid wait"1" has"git" for \
    depth=1 \
    from"{{ choose_github_mirror() }}" \
    atclone"git submodule set-url templates https://{{ choose_github_mirror() }}/github/gitignore.git" \
    voronkovich/gitignore.plugin.zsh

omz_git_plugins=(
    plugins/git/\*.zsh
    plugins/git-auto-fetch/\*.zsh
    plugins/git-extras/\*.zsh
    plugins/git-flow/\*.zsh
    plugins/gitignore/\*.zsh
)
# gf 用的少还跟 GoFrame 冲突, 所以不用
zi lucid wait'1' has"git" for \
    multisrc"$omz_git_plugins" \
    pick"/dev/null" \
    atload'unalias gf' \
    from"{{ choose_github_mirror() }}" \
    ohmyzsh/ohmyzsh

# 高级 Diff
zi lucid wait'1' has"diff-so-fancy" for \
    depth"1" \
    from"{{ choose_github_mirror() }}" \
    null \
    sbin'bin/git-dsf;bin/diff-so-fancy;bin/fancy-diff;' \
    z-shell/zsh-diff-so-fancy

# gh GitHub 官方 CLI
zi lucid wait'1' has"gh" for \
    id-as"gh_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"gh completion -s zsh > _gh; zi creinstall -q gh_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null

# act 模拟 GitHub Actions
# zi lucid wait'1' has"act" for \
#     id-as"act_completion" \
#     from"{{ choose_github_mirror() }}" \
#     as"completion" \
#     atclone"act completion -s zsh > _act; zi creinstall -q act_completion" \
#     atpull"%atclone" \
#     run-atpull \
#     z-shell/null

# glab GitLab 官方 CLI
zi lucid wait'1' has"glab" for \
    id-as"glab_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"glab completion -s zsh > _glab; zi creinstall -q glab_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null

### Git-结束
