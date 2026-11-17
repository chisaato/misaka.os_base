"""独占 Fedora 43 VM 的真实下载/重启故障注入，随后交给 run.py 做已升级恢复。"""
from __future__ import annotations

import json
import os
import shlex
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
    ssh = ['ssh', '-i', host['ansible_ssh_private_key_file'], '-o', 'StrictHostKeyChecking=no',
           '-o', 'UserKnownHostsFile=/dev/null', '-o', 'ConnectTimeout=5',
           f"{host['ansible_user']}@{host['ansible_host']}"]
    env = dict(os.environ, ANSIBLE_COLLECTIONS_PATH=str(REPO / '.dev'))
    command = [str(REPO / '.venv/bin/ansible-playbook'), '-i', str(inventory), str(HERE / 'advance.yml')]
    results = []

    def guest(code):
        return subprocess.run(ssh + ['sudo python3 -c ' + shlex.quote(code)],
                              capture_output=True, text=True, check=True).stdout.strip()

    def snapshot():
        return json.loads(guest(
            "import json,pathlib,tomllib; p=pathlib.Path('/usr/lib/sysimage/libdnf5/offline/offline-transaction-state.toml'); "
            "print(json.dumps({'marker':json.loads(pathlib.Path('/var/lib/misaka/dist-upgrade/fedora.json').read_text()),"
            "'boot':pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),"
            "'os':dict(line.split('=',1) for line in pathlib.Path('/etc/os-release').read_text().splitlines() if '=' in line)['VERSION_ID'].strip(chr(34)),"
            "'state':tomllib.loads(p.read_text()) if p.exists() else None}))"))

    def record(case, observed):
        results.append({'case':case,'passed':True,'observed':observed})
        (output / 'staged-results.json').write_text(json.dumps(results, indent=2))

    def launch(case, until, gate_task=None):
        gate = output / (case + '.gate')
        assert not gate.exists(), '不要覆盖旧故障证据，请使用新运行目录'
        extra = {'fedora_dist_upgrade_until':until, 'fedora_dist_upgrade_lock_lease_seconds':60}
        child_env = dict(env)
        if gate_task:
            child_env.update(ANSIBLE_CALLBACK_PLUGINS=str(HERE / 'callback_plugins'),
                             ANSIBLE_CALLBACKS_ENABLED='upgrade_gate', UPGRADE_GATE_TASK=gate_task,
                             UPGRADE_GATE_FILE=str(gate))
        log = (output / (case + '.log')).open('w')
        process = subprocess.Popen(command + ['-e',json.dumps(extra)], env=child_env,
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        if gate_task:
            deadline = time.monotonic() + 1800
            while not gate.exists():
                assert process.poll() is None, (case, process.returncode)
                assert time.monotonic() < deadline, (case, 'gate timeout')
                time.sleep(0.3)
        return process

    def kill(process):
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()

    before = snapshot()
    assert before['os'] == '43' and before['marker']['stage'] == 'prepared'
    # R1：真实角色已写 download intent，但在启动 dnf 之前杀控制机。
    process = launch('R1-before-download-kill', 'downloaded', '下载目标版本的离线升级事务')
    kill(process)
    stopped = snapshot()
    assert stopped['marker']['stage'] == 'prepared' and stopped['marker']['intent']['action'] == 'download'
    time.sleep(62)
    assert launch('R1-download-resume', 'downloaded').wait(timeout=1800) == 0
    downloaded = snapshot()
    assert downloaded['marker']['stage'] == 'downloaded'
    assert downloaded['state']['offline-transaction-state']['target_releasever'] == '44'
    record('R1-controller-before-download', {'stage':'downloaded','limitation':'在 dnf 启动前杀控制机，不覆盖下载进行中'})

    # R4：普通 reboot 不触发 offline transaction，保留 downloaded。
    reboot = subprocess.run(ssh + ['sudo systemctl reboot'], capture_output=True)
    assert reboot.returncode in [0,255]
    deadline = time.monotonic() + 300
    while True:
        try:
            after = snapshot()
            if after['boot'] != downloaded['boot']:
                break
        except subprocess.CalledProcessError:
            pass
        assert time.monotonic() < deadline, '普通 reboot 未恢复'
        time.sleep(2)
    assert after['os'] == '43'
    assert launch('R4-after-manual-reboot', 'downloaded').wait(timeout=180) == 0
    assert snapshot() == after
    record('R4-manual-reboot', {'os':'43','stage':'downloaded','boot_changed':True})

    # R7：真实清理 dnf 待办事务，角色必须记录降级后重下。
    subprocess.run(ssh + ['sudo dnf5 offline clean'], check=True, capture_output=True)
    assert launch('R7-clean-pending-resume', 'downloaded').wait(timeout=1800) == 0
    cleaned = snapshot()
    assert cleaned['marker']['stage'] == 'downloaded'
    assert any(row['result'] == 'demoted' for row in cleaned['marker']['history'])
    record('R7-offline-clean', {'stage':'downloaded','demoted':True})

    # R2：intent 已落盘，真正 dnf offline reboot 尚未发出。
    process = launch('R2-before-offline-reboot-kill', 'completed', '执行 dnf5 offline reboot')
    kill(process)
    intent = snapshot()
    assert intent['marker']['stage'] == 'reboot_requested'
    assert intent['os'] == '43' and intent['boot'] == cleaned['boot']
    record('R2-intent-before-reboot', {'stage':'reboot_requested','boot_unchanged':True})
    time.sleep(62)

    # R3：同一 operation 重发未执行的 reboot；guest 升级后控制机在 verify 前丢失。
    process = launch('R3-after-offline-reboot-kill', 'completed', '重启后重新采集事实')
    upgraded = snapshot()
    assert upgraded['os'] == '44' and upgraded['boot'] != intent['boot']
    assert upgraded['marker']['operation_id'] == before['marker']['operation_id']
    kill(process)
    assert launch('R3-fresh-controller-resume', 'completed').wait(timeout=1800) == 0
    finished = snapshot()
    assert finished['marker']['stage'] == 'completed'
    assert finished['boot'] == upgraded['boot']
    record('R3-controller-lost-after-upgrade', {'os':'44','operation_unchanged':True,'second_reboot':False})
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
