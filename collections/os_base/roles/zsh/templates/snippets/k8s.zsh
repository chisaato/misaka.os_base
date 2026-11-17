### K8S 官方仓库的命令部分-开始

# kubectl 插件与补全
zi lucid wait'1' has"kubectl" for \
    id-as"kubectl_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"kubectl completion zsh > _kubectl; zi creinstall -q kubectl_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null

# 加载 Kubeadm
zi lucid wait'1' has"kubeadm" for \
    id-as"kubeadm_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"kubeadm completion zsh > _kubeadm; zi creinstall -q kubeadm_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null

# 加载 minikube
zi lucid wait'1' has"minikube" for \
    id-as"minikube_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"minikube completion zsh > _minikube; zi creinstall -q minikube_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null

# 加载 OMZ kubectl 插件
zi lucid wait'1' has"kubectl"  for \
    multisrc"plugins/kubectl/*.zsh" \
    pick"/dev/null" \
    from"{{ choose_github_mirror() }}" \
    ohmyzsh/ohmyzsh
### K8S 官方仓库的命令部分-结束

### K8S 其他相关命令部分-开始

# Cilium
zi lucid wait'1' has"cilium" for \
    id-as"cilium_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"cilium completion zsh > _cilium; zi creinstall -q cilium_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null

# Cilium 的附属 hubble
zi lucid wait'1' has"hubble" for \
    id-as"hubble_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"hubble completion zsh > _hubble; zi creinstall -q hubble_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null

# 加载 helm
zi lucid wait'1' has"helm" for \
    id-as"helm_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"helm completion zsh > _helm; zi creinstall -q helm_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null

# 加载 helm chart-releaser
zi lucid wait'1' has"cr" for \
    id-as"cr_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"cr completion zsh > _cr; zi creinstall -q cr_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null

# 加载 helm chart-testing
zi lucid wait'1' has"ct" for \
    id-as"ct_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"ct completion zsh > _ct; zi creinstall -q ct_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null

# 加载 istioctl
zi lucid wait'1' has"istioctl" for \
    id-as"istioctl_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"istioctl completion zsh > _istioctl; zi creinstall -q istioctl_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null

# 加载 kind
zi lucid wait'1' has"kind" for \
    id-as"kind_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"kind completion zsh > _kind; zi creinstall -q kind_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null

# argocd ArgoCD 的官方 CLI
zi lucid wait'1' has"argocd" for \
    id-as"argocd_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"argocd completion zsh > _argocd; zi creinstall -q argocd_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null

# argo ArgoCD 的另一个管理工具
zi lucid wait'1' has"argo" for \
    id-as"argo_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"argo completion zsh > _argo; zi creinstall -q argo_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null

# Flux CD 持续交付工具
zi lucid wait'1' has"flux" for \
    id-as"flux_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"flux completion zsh > _flux; zi creinstall -q flux_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null

# Velero 备份工具
zi lucid wait'1' has"velero" for \
    id-as"velero_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"velero completion zsh > _velero; zi creinstall -q velero_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null

# Skaffold 快速迭代
zi lucid wait'1' has"skaffold" for \
    id-as"skaffold_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"skaffold completion zsh > _skaffold; zi creinstall -q skaffold_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null
# Telepresence 流量镜像
zi lucid wait'1' has"telepresence" for \
    id-as"telepresence_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"telepresence completion zsh > _telepresence; zi creinstall -q telepresence_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null

### K8S 其他相关命令部分-结束

### Krew 插件-开始

# 这里的补全不仅是补全,还要做软链接和补全别名定义.

# kubecm 多集群配置管理工具
zi lucid wait'1' has"kubectl-kc" for \
    id-as"kubecm_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"kubectl-kc completion zsh > _kubecm; zi creinstall -q kubecm_completion" \
    atinit"ln -sf $HOME/.krew/bin/kubectl-kc $ZPFX/bin/kubecm;
    compdef _kubecm kubectl-kc;
    echo '#!/bin/sh\nkubectl-kc __complete \"\$@\"' > $HOME/.krew/bin/kubectl_complete-kc;
    chmod +x $HOME/.krew/bin/kubectl_complete-kc" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null

# virtctl kubeVirt 虚拟机管理
zi lucid wait'1' has"kubectl-virt" for \
    id-as"virtctl_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"kubectl-virt completion zsh > _virtctl; zi creinstall -q virtctl_completion" \
    atinit"ln -sf $HOME/.krew/bin/kubectl-virt $ZPFX/bin/virtctl;
    compdef _virtctl kubectl-virt;
    echo '#!/bin/sh\nkubectl-virt __complete \"\$@\"' > $HOME/.krew/bin/kubectl_complete-virt;
    chmod +x $HOME/.krew/bin/kubectl_complete-virt" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null
# pv-migrate 卷迁移
zi lucid wait'1' has"kubectl-pv_migrate" for \
    id-as"pv-migrate_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"kubectl-pv_migrate completion zsh > _pv-migrate; zi creinstall -q pv-migrate_completion" \
    atinit"ln -sf $HOME/.krew/bin/kubectl-pv_migrate $ZPFX/bin/pv-migrate;
    compdef _pv-migrate kubectl-pv_migrate;
    echo '#!/bin/sh\nkubectl-pv_migrate __complete \"\$@\"' > $HOME/.krew/bin/kubectl_complete-pv_migrate;
    chmod +x $HOME/.krew/bin/kubectl_complete-pv_migrate" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null

# Krew kubectl 插件管理器
zi lucid wait'1' has"kubectl-krew" for \
    id-as"krew_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"kubectl-krew completion zsh > _krew; zi creinstall -q krew_completion" \
    atinit"ln -sf $HOME/.krew/bin/kubectl-krew $ZPFX/bin/krew;compdef _krew kubectl-krew;
    echo '#!/bin/sh\nkubectl-krew __complete \"\$@\"' > $HOME/.krew/bin/kubectl_complete-krew;
    chmod +x $HOME/.krew/bin/kubectl_complete-krew" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null
### Krew 插件-结束

## 其他 K8S 开发工具-开始

# OperatorSDK 开发工具
zi lucid wait'1' has"operator-sdk" for \
    id-as"operator-sdk_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"operator-sdk completion zsh > _operator-sdk; zi creinstall -q operator-sdk_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null

# Chainsaw Operator 的端到端测试工具
zi lucid wait'1' has"chainsaw" for \
    id-as"chainsaw_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"chainsaw completion zsh > _chainsaw; zi creinstall -q chainsaw_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null

# pack Cloudnative Buildpacks
zi lucid wait'1' has"pack" for \
    id-as"pack_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"cat \$(pack completion --shell zsh) > _pack; zi creinstall -q pack_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null
# acloud-toolkit 一套好用的工具包
zi lucid wait'1' has"acloud-toolkit" for \
    id-as"acloud-toolkit_completion" \
    from"{{ choose_github_mirror() }}" \
    as"completion" \
    atclone"acloud-toolkit completion zsh > _acloud-toolkit; zi creinstall -q acloud-toolkit_completion" \
    atpull"%atclone" \
    run-atpull \
    z-shell/null
## 其他 K8S 开发工具-结束