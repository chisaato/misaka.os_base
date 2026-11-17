# misaka.containers.docker

此角色负责在 Debian、Fedora、Proxmox VE 等系统上安装并配置 Docker CE 或 Podman 容器运行时环境。

## 特性

- **多运行时支持**：支持原生 Docker CE 与 Podman（Fedora 默认推荐使用 Podman）。
- **国内镜像与加速优化**：支持配置 Docker Hub 及第三方 Registry（GCR、GHCR、Quay、K8S 等）镜像加速。
- **空安全设计**：即使清空所有镜像站点配置，角色和生成的配置文件均能安全稳定运行，自动回退到官方直连。

## 变量说明

| 变量名 | 默认值 | 说明 |
|---|---|---|
| `docker_use_podman` | `ansible_facts['distribution'] == 'Fedora'` | 是否使用 Podman 替代 Docker |
| `docker_registry_mirror` | `["https://hub-proxy.zdr.ac.cn"]` | Docker Hub 镜像加速站列表（带 `https://` 前缀） |
| `docker_podman_registry_mirror` | `{}` | Podman 额外的第三方 Registry 镜像加速站映射字典 |
| `docker_enable_ipv6` | `false` | 是否开启 IPv6 支持 |
| `docker_enable_firewall` | `true` | 是否允许 Docker 管理防火墙规则 |
| `docker_enable_podman_docker` | `false` | 是否安装 `podman-docker` 模拟包 |

## 镜像加速配置示例

### 1. Docker Hub 镜像加速 (`docker_registry_mirror`)

适用于 dockerd (`/etc/docker/daemon.json`) 和 podman (`/etc/containers/registries.conf.d/555-mirrors.conf`)：

```yaml
docker_registry_mirror:
  - https://hub-mirror.example.com
  - https://hub-mirror2.example.com:8443
```

若希望完全直连不使用任何 mirror，可直接定义为空列表：

```yaml
docker_registry_mirror: []
```

### 2. Podman 多源镜像加速 (`docker_podman_registry_mirror`)

由于第三方 Registry（如 `gcr.io`、`ghcr.io`、`quay.io` 等）公网较少有长期公开的镜像源，通常需要配合个人自建的 Registry 代理或反向代理服务使用。

配置格式与 K3s 的 `registries.yaml` 类似，**endpoint 地址不要带有 `https://` 前缀**，支持携带端口：

```yaml
docker_podman_registry_mirror:
  docker.elastic.co:
    endpoint:
      - elastic-mirror.example.com
      - mirror.example.com:8443
    remark: Elastic
  gcr.io:
    endpoint:
      - gcr-mirror.example.com
    remark: GCR
  ghcr.io:
    endpoint:
      - ghcr-mirror.example.com
    remark: GHCR
  quay.io:
    endpoint:
      - quay-mirror.example.com
    remark: Quay
  registry.k8s.io:
    endpoint:
      - k8s-mirror.example.com
    remark: K8S
  nvcr.io:
    endpoint:
      - nvcr-mirror.example.com
    remark: NVCR
  lscr.io:
    endpoint:
      - lscr-mirror.example.com
    remark: LinuxServer.io
  mcr.microsoft.com:
    endpoint:
      - mcr-mirror.example.com
    remark: Microsoft
  registry.developers.crunchydata.com:
    endpoint:
      - crunchydata-mirror.example.com
    remark: CrunchyData
  registry.gitlab.com:
    endpoint:
      - gitlab-mirror.example.com
    remark: GitLab
  codeberg.org:
    endpoint:
      - codeberg-mirror.example.com
    remark: Codeberg
```
