"""Filestore (attachment binaries) copy into the Odoo container."""

import os
import subprocess


def copy_filestore(filestore_src, target_db, odoo_container):
    """Copy the extracted Enterprise filestore into the Odoo container.

    The Enterprise SaaS dump ships its filestore as a sibling directory of
    `dump.sql`. Odoo expects it under
    `<data_dir>/filestore/<dbname>` inside the container.
    """
    if not os.path.isdir(filestore_src):
        print(f"  WARNING: Filestore not found at {filestore_src}")
        return False

    print(f"  Copying filestore from {filestore_src} ...")
    dest = f"/var/lib/odoo/filestore/{target_db}"

    for cmd in [
        f"docker exec {odoo_container} rm -rf {dest}",
        f"docker exec {odoo_container} mkdir -p {dest}",
        f"tar -cf - -C {filestore_src} . | docker exec -i {odoo_container} tar -xf - -C {dest}",
        f"docker exec {odoo_container} chown -R odoo:odoo /var/lib/odoo/filestore/{target_db}",
    ]:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  WARNING: failed: {r.stderr[:200]}")
            return False

    r = subprocess.run(
        f"docker exec {odoo_container} find {dest} -type f | wc -l",
        shell=True, capture_output=True, text=True,
    )
    print(f"  Filestore: {r.stdout.strip()} files copied")
    return True
