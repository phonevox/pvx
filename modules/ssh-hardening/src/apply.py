import json
from datetime import datetime
from pathlib import Path

import sudoers
import user_setup
from backup import backup_config
from sshd_config import set_directive
from sshd_validate import apply_with_rollback


def apply(plan, config_path, sudoers_dir, state_dir):
    if plan is None:
        return {"applied": False}

    config_path = Path(config_path)
    backup_path = str(backup_config(str(config_path))) if config_path.exists() else None
    config_text = config_path.read_text() if config_path.exists() else ""

    if plan["lock_root"]:
        user_setup.set_password("root", plan["root_password"])
        config_text = set_directive(config_text, "PermitRootLogin", "no")

    if plan["create_user"]:
        username = plan["username"]
        user_setup.create_user(username)
        user_setup.add_to_admin_group(username)
        sudoers.install_rule(username, sudoers_dir=sudoers_dir)
        user_setup.setup_authorized_key(f"/home/{username}", username, plan["public_key"])
        if plan["allow_password"]:
            user_setup.set_password(username, plan["user_password"])

    if plan["change_port"]:
        config_text = set_directive(config_text, "Port", plan["port"])

    config_path.write_text(config_text)

    config_valid = apply_with_rollback(str(config_path), backup_path) if backup_path else True

    record_dir = Path(state_dir)
    record_dir.mkdir(parents=True, exist_ok=True)
    record_path = record_dir / f"apply-{datetime.now():%Y%m%d_%H%M%S}.json"
    record = {"plan": plan, "config_valid": config_valid, "backup_path": backup_path}
    record_path.write_text(json.dumps(record, indent=2))
    record_path.chmod(0o600)

    return {"applied": True, "config_valid": config_valid, "record_path": str(record_path)}
