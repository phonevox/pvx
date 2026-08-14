import secrets

from validators import validate_port, validate_public_key, validate_username

DEFAULT_ROOT_PASSWORD = "phonevox@@"
DEFAULT_USERNAME = "phonevox"
DEFAULT_PUBLIC_KEY = 'ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQC5S9t+CHuQYVe9It/zVWNEYWq7fuGBF1oll63MujAREeP3sB3NVhrWs8AcDNOwPQ+8Z7s4Yc8/r8BKCquujugkWv3ilZjJAbeyR7A6rddRM1ai1bfc8gRV7CD1tExQuO+QE9RORQ0f0J+0+Fu4vB3YRMeSx4czq5tbYKwvdfP6pgWWRppyA8uM7nKXnYsdwkyKxJZb4I353cC4C+ZvaEUQahygNs9XgblBB9TM0UuttdoBi4pTj4aqLXTBhcLqghkQP45JaQ8/G5qSzs2U2eGH4L+mEqFSg+ybL3KxGmyHxtCBOqhFTm/s3EqkSQ80OSwdYSzH7GMTWWfKZ4UoeFiQucHYto83LmfBYdqckbtw7ZNsXU/egQR5eSwtwQBK5yLnPSnQldozMKoS2gKayWtxqvjiYpQacw48DaB1mZUfl7SJ/fa9LEUrQ2CnizQJSemwsteJqDII95mzCpyGXAeNfXdhI52dx0YXx3D62LXQBAn1HSIgnzsrEVh29CumZ28cxpOL0djI2Y8VyHgw6fFSAZqmn3Xr2yCxBvzN4rlEvtzGVw8PxAZT33duLEgPFV2XBrU5I98bufgg8cE3NXTLtMwuYWbtKtbRZkpRJesQEkaL70kLvvsYCZAaqDhwLAO8q41czunYLt6MyKcAHrb5whFBz6Fx/WrEEpM1p5KhSw== MAIN@PHONEVOX'
DEFAULT_PORT = "21122"


def build_plan(
    lock_root, root_password,
    create_user, username, public_key, allow_password, user_password,
    change_port, port,
):
    if not (lock_root or create_user or change_port):
        return None

    if create_user:
        username = username or DEFAULT_USERNAME
        public_key = public_key or DEFAULT_PUBLIC_KEY
        if not validate_username(username):
            raise ValueError(f"username inválido: {username}")
        if not validate_public_key(public_key):
            raise ValueError(f"chave pública inválida: {public_key}")
        if allow_password:
            user_password = user_password or secrets.token_hex(12)
        else:
            user_password = None
    else:
        username = public_key = user_password = None

    if change_port:
        port = port or DEFAULT_PORT
        if not validate_port(port):
            raise ValueError(f"porta inválida: {port}")
    else:
        port = None

    root_password = (root_password or DEFAULT_ROOT_PASSWORD) if lock_root else None

    return {
        "lock_root": lock_root,
        "root_password": root_password,
        "create_user": create_user,
        "username": username,
        "public_key": public_key,
        "allow_password": allow_password,
        "user_password": user_password,
        "change_port": change_port,
        "port": port,
    }
