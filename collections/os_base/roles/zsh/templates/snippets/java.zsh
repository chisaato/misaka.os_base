### Java-开始

if [ -e "${SDKMAN_DIR}/bin/sdkman-init.sh" ];then
    source "${SDKMAN_DIR}/bin/sdkman-init.sh"
fi

# 加载 SDKMAN 插件
zi lucid wait'1' for \
    depth"1" \
    from"{{ choose_github_mirror() }}" \
    if'[ -s "$HOME/.sdkman/bin/sdkman-init.sh" ]' \
    matthieusb/zsh-sdkman

# 加载 Gradle
zi lucid wait'1' has"java" for \
    multisrc"plugins/gradle/*.zsh" \
    pick"/dev/null" \
    from"{{ choose_github_mirror() }}" \
    ohmyzsh/ohmyzsh

### Java-结束
