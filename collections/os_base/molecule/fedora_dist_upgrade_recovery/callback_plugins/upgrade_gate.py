"""只用于 VM 故障注入：在指定 Ansible 任务之前阻塞控制机。"""
import os
import time
from pathlib import Path

from ansible.plugins.callback import CallbackBase


class CallbackModule(CallbackBase):
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = "aggregate"
    CALLBACK_NAME = "upgrade_gate"
    CALLBACK_NEEDS_ENABLED = True

    def v2_playbook_on_task_start(self, task, is_conditional):
        wanted = os.environ.get("UPGRADE_GATE_TASK")
        event = os.environ.get("UPGRADE_GATE_FILE")
        if not wanted or not event or wanted not in task.get_name():
            return
        path = Path(event)
        if path.exists():
            return
        path.write_text(task.get_name(), encoding="utf-8")
        deadline = time.monotonic() + 120
        while not Path(event + ".release").exists():
            if time.monotonic() > deadline:
                raise RuntimeError("恢复测试的控制机闸门超时")
            time.sleep(0.1)
