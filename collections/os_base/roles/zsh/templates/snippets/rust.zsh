### Rust-开始

# 尝试加载 Rustup
if [ -s "$HOME/.cargo/bin/rustup" ]; then
    source ~/.cargo/env
    export RUST_SYSROOT=$(rustc --print sysroot)
fi

# rustup 补全
zi lucid wait'1' has"rustup" for \
    id-as"rustup_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"rustup completions zsh > _rustup; zi creinstall -q rustup_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null


# cargo 补全 注意还是从 rustup 加载的
zi lucid wait'1' has"rustup" for \
    id-as"cargo_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"cat $RUST_SYSROOT/share/zsh/site-functions/_cargo >> _cargo; zi creinstall -q cargo_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null

# 设置一些默认参数
zi default-ice -q lucid depth=1 from"{{ choose_github_mirror() }}"

# zi lucid wait'1' has"rustup" for \
#     @rust-utils

zi default-ice -cq
### Rust-结束
