# Fedora Docker CE 软件源按 geo 切换 DNF5 override

Fedora 的 `/etc/yum.repos.d/docker-ce.repo` 由 docker role 渲染，并非
RPM 包拥有的 `%config` 文件，因此始终完整渲染官方 `baseurl` 和官方
`gpgkey`；国内镜像仅通过
`/etc/dnf/repos.override.d/40-misaka-docker-ce.repo` 覆盖现有 repo id。
override 中成对写入 `baseurl=`（清除官方地址）与国内本地 `mirrorlist=`；
保留原文件的 enabled、gpgcheck 等选项。官方 GPG key 体量小且签名校验
与下载镜像站无关，不再使用国内站烘焙的 key URL。

原实现仅在 CN 渲染 mirrorlist；主机 geo 转海外后会留下孤儿文件。
现在非 CN 删除本角色的 override，且只清理
`/etc/dnf/mirrorlist/docker-ce-*.mirrorlist`；不会触及 Fedora、
RPMFusion 或其他用户的 mirrorlist。repo id 和 mirrorlist 路径统一由
`docker_ce_repos` 提供，Fedora Podman 与 Docker 路径共用同一任务。
Debian apt 没有 DNF override，继续原有烘焙方式。

若 Fedora 46 以后 Docker 官方将 repo 文件改由 RPM `%config` 管理，
应先检查所有权和默认 repo 位置，再改为保留 vendor 原文件、仅渲染
override；目前不提前删除角色拥有的完整定义。
