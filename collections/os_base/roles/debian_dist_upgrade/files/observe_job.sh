#!/bin/sh
# 在线升级连 systemctl 的共享库都可能暂时不可用；此时只能报忙，不能当作结束。
# 使用 shell 内建解析本角色写入的固定 JSON 格式，不依赖正在替换的 Python/grep/cat。
active=/var/lib/misaka/dist-upgrade/debian-jobs/active.json
if [ ! -f "$active" ]; then
    [ -z "${expected_stage:-}" ] && exit 0
    printf '%s\n' 'needs_human: 缺少对应的持久 worker，需人工检查' >&2
    exit 2
fi
unit=
while IFS= read -r line; do
    case "$line" in
        *'"unit": "'*) unit=${line#*'"unit": "'}; unit=${unit%%'"'*} ;;
    esac
done < "$active"
case "$unit" in
    misaka-debian-prepare-*|misaka-debian-download-*|misaka-debian-minimal-*|misaka-debian-full-*) ;;
    *) printf '%s\n' 'needs_human: 活跃单元名称非法，拒绝继续' >&2; exit 2 ;;
esac
id=${unit##*-}
case "$id" in
    *[!0123456789abcdef]*|'') printf '%s\n' 'needs_human: job ID 非法，拒绝继续' >&2; exit 2 ;;
esac
if [ "${#id}" -ne 32 ]; then
    printf '%s\n' 'needs_human: job ID 长度非法，拒绝继续' >&2
    exit 2
fi
stage=${unit#misaka-debian-}
stage=${stage%-*}
if [ -n "${expected_stage:-}" ] && [ "$stage" != "$expected_stage" ]; then
    printf '%s\n' 'needs_human: worker 阶段不匹配，拒绝继续' >&2
    exit 2
fi
result="/var/lib/misaka/dist-upgrade/debian-jobs/$id.json"
# 结果在 APT 已退出且 marker 已写完后原子生成；重启后 transient 单元可不存在。
if [ -s "$result" ]; then
    ok=false
    while IFS= read -r line; do
        printf '%s\n' "$line"
        case "$line" in *'"ok": true'*) ok=true ;; esac
    done < "$result"
    [ "$ok" = true ] && exit 0
    printf '%s\n' 'needs_human: worker 失败，需人工检查；不自动修复或重启安装' >&2
    exit 2
fi
if state=$(systemctl show "$unit" --property=ActiveState --value 2>&1); then
    case "$state" in
        active|activating|reloading) printf 'busy: %s\n' "$unit"; exit 75 ;;
        *) printf '%s\n' 'needs_human: worker 已退出但没有持久结果，需人工检查' >&2; exit 2 ;;
    esac
fi
printf 'busy: 观察命令暂不可用，不能认定事务结束（%s）：%s\n' "$unit" "$state"
exit 75
