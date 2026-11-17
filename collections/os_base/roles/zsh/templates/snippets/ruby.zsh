### Ruby-开始

# RVM
# 首先是加载 RVM
# [[ -s "$HOME/.rvm/scripts/rvm" ]] && . "$HOME/.rvm/scripts/rvm"
# 然后加载插件,需要注意这里有一个加载补全要用 zpcdreplay 解决一下
# zi lucid wait'1' has"rvm" for \
#     from"{{ choose_github_mirror() }}" \
#     atload"export PATH="$PATH:$HOME/.rvm/bin"" \
#     atload"zpcdreplay" \
#     multisrc"plugins/rvm/*.zsh" \
#     pick"/dev/null" \
#     from"{{ choose_github_mirror() }}" \
#     ohmyzsh/ohmyzsh

# Ruby 一些别名,意义不大
# zi lucid wait'1' has"ruby" for \
#     from"{{ choose_github_mirror() }}" \
#     OMZP::ruby

### Ruby-结束
