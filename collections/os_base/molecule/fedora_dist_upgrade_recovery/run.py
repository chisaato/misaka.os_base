"""在独占的已升级 VM 上运行控制机故障与拒绝用例；不创建或销毁域。

用法：uv run python .../run.py inventory.yml /tmp/opencode/recovery
日志和机器可读结果均留在指定目录。任何失败保留现场，不继续注入。
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import yaml


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]


def main():
    inventory = Path(sys.argv[1]).resolve()
    output = Path(sys.argv[2]).resolve()
    output.mkdir(parents=True, exist_ok=True)
    host = next(iter(yaml.safe_load(inventory.read_text())["all"]["hosts"].values()))
    ssh = ["ssh", "-i", host["ansible_ssh_private_key_file"], "-o", "StrictHostKeyChecking=no",
           "-o", "UserKnownHostsFile=/dev/null", f"{host['ansible_user']}@{host['ansible_host']}"]
    env = dict(os.environ, ANSIBLE_COLLECTIONS_PATH=str(REPO / ".dev"))
    command = [str(REPO / ".venv/bin/ansible-playbook"), "-i", str(inventory), str(HERE / "advance.yml")]
    results = []

    def guest(code, data=None):
        proc = subprocess.run(ssh + ["sudo python3 -c " + __import__('shlex').quote(code)],
                              input=json.dumps(data) if data is not None else None,
                              capture_output=True, text=True, check=True)
        return proc.stdout.strip()

    def snapshot():
        return json.loads(guest("import json,pathlib; p=pathlib.Path('/var/lib/misaka/dist-upgrade/fedora.json'); "
                                "print(json.dumps({'marker':json.loads(p.read_text()),'boot':pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()}))"))

    def inject(marker):
        guest("import json,sys,os,pathlib; p=pathlib.Path('/var/lib/misaka/dist-upgrade/fedora.json'); "
              "t=p.with_suffix('.injection'); t.write_text(json.dumps(json.load(sys.stdin))); os.chmod(t,0o600); t.replace(p)", marker)

    def run(case, extra=None, extra_env=None):
        log = (output / f"{case}.log").open("w")
        args = command + (["-e", json.dumps(extra)] if extra else [])
        return subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT,
                                env=dict(env, **(extra_env or {})), start_new_session=True)

    def checked(case, extra, expected):
        before = snapshot()
        proc = run(case, extra)
        rc = proc.wait(timeout=180)
        after = snapshot()
        assert (rc == 0) == expected, (case, rc)
        if not expected:
            assert before == after, f"{case}: 拒绝时 marker 或 boot_id 发生了变化"
        results.append({"case":case,"rc":rc,"seq":after['marker']['seq'],"boot":after['boot'],"passed":True})
        (output / 'results.json').write_text(json.dumps(results, indent=2))

    original = snapshot()
    (output / 'original.json').write_text(json.dumps(original, indent=2))
    assert original['marker']['stage'] == 'completed'
    checked('R9-target-conflict', {'fedora_dist_upgrade_target_release':43}, False)
    wrong = dict(original['marker'], machine={'id_sha256_16':'another-machine'})
    inject(wrong)
    checked('R10-machine-conflict', {}, False)
    inject(original['marker'])

    # R13：第一个完整 advance 在取得目录锁之后、事务探测之前暂停。
    gate = output / 'controller-gate'
    first = run('R13-controller-a', {'fedora_dist_upgrade_lock_lease_seconds':60}, {
        'ANSIBLE_CALLBACK_PLUGINS':str(HERE / 'callback_plugins'),
        'ANSIBLE_CALLBACKS_ENABLED':'upgrade_gate',
        'UPGRADE_GATE_TASK':'清除上一步留下的 marker 补丁',
        'UPGRADE_GATE_FILE':str(gate)})
    deadline = time.monotonic() + 90
    while not gate.exists():
        assert first.poll() is None, '控制机 A 未到达持锁闸门即退出'
        assert time.monotonic() < deadline, '持锁闸门超时'
        time.sleep(0.2)
    checked('R13-controller-b-refused', {}, False)
    # R12：杀掉真正的控制机进程组，guest 锁不能立即无条件接管。
    os.killpg(first.pid, signal.SIGKILL)
    first.wait()
    time.sleep(62)
    checked('R12-expired-controller-takeover', {}, True)
    # 独立核对：恢复没有重启或改变已完成 operation。
    final = snapshot()
    assert final['boot'] == original['boot']
    assert final['marker']['operation_id'] == original['marker']['operation_id']
    assert final['marker']['seq'] == original['marker']['seq'] + 1
    assert final['marker']['history'][-1]['result'] == 'takeover'
    results.append({'case':'R12/R13-full-advance','passed':True,'limitation':'completed 状态事务；不证明下载或重启窗口'})
    (output / 'results.json').write_text(json.dumps(results, indent=2))

    # R6：已核验的同一系统，恢复到 verified，控制机在第一个 finalize 任务前被杀。
    verified = dict(final['marker'], stage='verified')
    inject(verified)
    finalize_gate = output / 'finalize-gate'
    interrupted = run('R6-finalize-interrupted', {'fedora_dist_upgrade_lock_lease_seconds':60}, {
        'ANSIBLE_CALLBACK_PLUGINS':str(HERE / 'callback_plugins'),
        'ANSIBLE_CALLBACKS_ENABLED':'upgrade_gate',
        'UPGRADE_GATE_TASK':'安装升级后的清理工具',
        'UPGRADE_GATE_FILE':str(finalize_gate)})
    deadline = time.monotonic() + 90
    while not finalize_gate.exists():
        assert interrupted.poll() is None, 'R6 控制机提前退出'
        assert time.monotonic() < deadline, 'R6 闸门超时'
        time.sleep(0.2)
    os.killpg(interrupted.pid, signal.SIGKILL)
    interrupted.wait()
    assert snapshot()['marker']['stage'] == 'verified'
    time.sleep(62)
    checked('R6-finalize-resumed', {}, True)
    finished = snapshot()
    assert finished['marker']['stage'] == 'completed'
    assert finished['boot'] == original['boot']
    assert finished['marker']['evidence']['reboot'] == original['marker']['evidence']['reboot']

    # R8：让 marker 落后于真实 OS，必须通过事实收养，不触发第二次离线重启。
    inject(dict(finished['marker'], stage='downloaded'))
    checked('R8-adopt-upgraded-facts', {}, True)
    adopted = snapshot()
    assert adopted['marker']['stage'] == 'completed'
    assert adopted['boot'] == original['boot']
    assert any(row['result'] == 'adopted' for row in adopted['marker']['history'])

    # R11：真实 guest 为 44，向控制机 jsonfile cache 注入旧的 43。
    cache = output / 'fact-cache'
    cache.mkdir()
    before_cache = snapshot()
    cache_env = dict(env, ANSIBLE_CACHE_PLUGIN='jsonfile', ANSIBLE_CACHE_PLUGIN_CONNECTION=str(cache))
    for play in ['cache_seed.yml', 'cache_resume.yml']:
        with (output / ('R11-' + play + '.log')).open('w') as log:
            assert subprocess.run(command[:-1] + [str(HERE / play)], stdout=log,
                                  stderr=subprocess.STDOUT, env=cache_env, timeout=180).returncode == 0
    assert snapshot() == before_cache
    results.append({'case':'R11-stale-fact-cache','passed':True,'observed':'completed/44'})
    (output / 'results.json').write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
