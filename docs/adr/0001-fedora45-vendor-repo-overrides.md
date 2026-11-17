# Fedora 45 vendor repo 使用 DNF5 override 层

Fedora 45 的 fedora-repos / rpmfusion release 包将 repo 移到
`/usr/share/dnf5/repos.d`，密钥移到 `/usr/share/pki/rpm-gpg`。
直接修改包文件可能在升级时保留为 `.rpmsave`。因此默认用 `rpm -V`
检查 vendor repo 与密钥的漂移，失败时要求人工检查或显式同意重装并复验。

DNF5 的 reposdir 对同 id 仅加载第一个定义：把精简 stanza 写进
`/etc/yum.repos.d` 会完整遮蔽 vendor 配置，而不是补充配置。
国内镜像改由 `/etc/dnf/repos.override.d/40-misaka-cn-mirror.repo`
覆盖已经存在的 vendor section；此层不创建 repo。实测仅写 `mirrorlist`
会被 vendor `metalink` 抢先，必须成对写入空 `metalink=` 和本地
`mirrorlist=file:///etc/dnf/mirrorlist/<id>.mirrorlist`。
DNF5 按字典序合并 override，后写选项覆盖前值；管理员的
`99-config-manager.repo` 可以再次覆盖。

非 vendor 的 rpmfusion tainted 仍保留完整 repo 定义。Fedora 43/44
继续原有模板渲染；仅检测到新 vendor 布局时删除旧版渲染的精确文件
及对应 `.rpmsave`，不扫描删除其他用户仓库。

升级下载使用 `dnf5 system-upgrade download --releasever=<目标>`，
vendor metalink 内的 `$releasever` 由 DNF 自行展开；海外无需临时
override。升级到 45 后重跑角色，以新版本重渲国内 mirrorlist，
并执行布局迁移。
