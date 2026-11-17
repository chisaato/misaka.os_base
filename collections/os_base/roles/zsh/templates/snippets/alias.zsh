### 别名-开始

alias freshZshCache="source ~/.zshrc"
{% if ansible_facts['distribution'] == 'Debian' and ansible_facts['distribution_major_version'] is version('11', '<') %}
{# 因为 debian 11 以前的 exa 都不具备 --icons #}
alias ls='exa'
{% endif %}
# sudo 保留别名
# alias sudo='sudo '
# sudo 保留变量
# alias sudo='sudo -E'
### 别名-结束
