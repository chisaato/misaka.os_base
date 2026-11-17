# pve_init

这适用于 PVE 系统装完后进行初始化  
也可以用于在 Debian 上安装的 PVE (当别人帮你装好的时候)

需要注意的是,这个包默认会自动调用 `debian_packages` 和 `debian_init` 来进行 Debian 相关部分的设置.

可以通过设定 `pve_init_auto_debian_init: false` 来关闭
